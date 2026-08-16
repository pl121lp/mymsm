package com.mymsm.extract;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

/**
 * Standalone, dependency-free reimplementation of the MSISAM ("new
 * encryption" Jet 4 / Microsoft Money) password check, reverse-engineered
 * from jackcess-encrypt 4.0.3's {@code MSISAMCryptCodecHandler}.
 *
 * <p>Checking a candidate this way costs one 40-byte digest plus a 4-byte
 * RC4 keystream comparison against a value cached from the file header —
 * no database open, no table catalog, no page decoding — so it is orders
 * of magnitude faster than testing candidates through the real extraction
 * pipeline (jackcess {@code DatabaseBuilder.open()}) one at a time. Used by
 * {@code PasswordCracker} for offline password search.
 *
 * <p>This only implements the "new encryption" MSISAM variant, which is
 * what this project's Money file uses (confirmed by the fact that it
 * throws {@code InvalidCredentialsException} rather than silently
 * decrypting garbage). It does not implement the older Jet3/pre-2000
 * obfuscation scheme, which doesn't use a user password at all.
 */
public final class MsisamPasswordCheck {

    private static final int SALT_OFFSET = 0x72;
    private static final int CRYPT_CHECK_START = 0x2e9;
    private static final int ENCRYPTION_FLAGS_OFFSET = 0x298;
    private static final int USE_SHA1_FLAG = 0x20;
    private static final int NEW_ENCRYPTION_FLAG = 0x6;
    private static final int PASSWORD_LENGTH_BYTES = 0x28;
    private static final int DIGEST_LENGTH = 0x10;
    private static final int HEADER_READ_LENGTH = 4096;

    private MsisamPasswordCheck() {
    }

    public static final class Header {
        final byte[] salt8;
        final byte[] baseSalt4;
        final byte[] encryptedCheck4;
        final boolean useSha1;
        final boolean newEncryption;

        Header(byte[] salt8, byte[] encryptedCheck4, boolean useSha1, boolean newEncryption) {
            this.salt8 = salt8;
            this.baseSalt4 = Arrays.copyOf(salt8, 4);
            this.encryptedCheck4 = encryptedCheck4;
            this.useSha1 = useSha1;
            this.newEncryption = newEncryption;
        }

        /** Fresh {@link MessageDigest} instance matching this file's hash algorithm. */
        public MessageDigest newDigest() {
            try {
                return MessageDigest.getInstance(useSha1 ? "SHA-1" : "MD5");
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException(e);
            }
        }
    }

    public static Header readHeader(File mnyFile) throws IOException {
        byte[] buf = new byte[HEADER_READ_LENGTH];
        try (RandomAccessFile raf = new RandomAccessFile(mnyFile, "r")) {
            int toRead = (int) Math.min(HEADER_READ_LENGTH, raf.length());
            raf.readFully(buf, 0, toRead);
        }
        return fromBuffer(buf);
    }

    static Header fromBuffer(byte[] buf) {
        int flags = buf[ENCRYPTION_FLAGS_OFFSET] & 0xFF;
        boolean useSha1 = (flags & USE_SHA1_FLAG) != 0;
        boolean newEncryption = (flags & NEW_ENCRYPTION_FLAG) != 0;

        byte[] salt8 = Arrays.copyOfRange(buf, SALT_OFFSET, SALT_OFFSET + 8);

        int cryptCheckOffset = salt8[0] & 0xFF;
        int checkStart = CRYPT_CHECK_START + cryptCheckOffset;
        byte[] encryptedCheck4 = Arrays.copyOfRange(buf, checkStart, checkStart + 4);

        return new Header(salt8, encryptedCheck4, useSha1, newEncryption);
    }

    /**
     * Returns true if {@code candidate} is the file's password. Case is
     * irrelevant to the underlying algorithm — passwords are uppercased
     * before hashing — so this is too. Convenience overload for one-off
     * checks; allocates a fresh {@link MessageDigest} internally.
     */
    public static boolean check(Header header, String candidate) {
        return check(header, candidate, header.newDigest());
    }

    /**
     * Same as {@link #check(Header, String)} but reuses a caller-supplied
     * {@link MessageDigest}, avoiding per-call provider lookup — use this
     * form in hot loops (e.g. brute-force search).
     */
    public static boolean check(Header header, String candidate, MessageDigest reusableDigest) {
        byte[] passwordBytes = new byte[PASSWORD_LENGTH_BYTES];
        if (candidate != null) {
            ByteBuffer encoded = StandardCharsets.UTF_16LE.encode(candidate.toUpperCase());
            int n = Math.min(passwordBytes.length, encoded.remaining());
            encoded.get(passwordBytes, 0, n);
        }
        return checkEncodedPassword(header, passwordBytes, reusableDigest);
    }

    /**
     * Lowest-level entry point: {@code passwordBytes} must already be the
     * exact 40-byte zero-padded UTF-16LE encoding of the uppercased
     * candidate (see {@link #encodeUppercaseLetters}). Used by the
     * brute-force worker to skip charset/String overhead entirely.
     */
    static boolean checkEncodedPassword(Header header, byte[] passwordBytes, MessageDigest reusableDigest) {
        byte[] digest = digest(passwordBytes, reusableDigest);

        byte[] key = new byte[digest.length + header.salt8.length];
        System.arraycopy(digest, 0, key, 0, digest.length);
        System.arraycopy(header.salt8, 0, key, digest.length, header.salt8.length);

        byte[] decrypted = rc4(key, header.encryptedCheck4);
        return Arrays.equals(decrypted, header.baseSalt4);
    }

    /**
     * Encodes a candidate already known to be uppercase A-Z letters only,
     * without going through {@link StandardCharsets#UTF_16LE}'s general
     * CharsetEncoder machinery. UTF-16LE of a plain ASCII letter is just
     * (letter byte, 0x00), so this is a direct byte-array fill.
     */
    static byte[] encodeUppercaseLetters(char[] upperLetters, int len) {
        byte[] passwordBytes = new byte[PASSWORD_LENGTH_BYTES];
        int n = Math.min(len, PASSWORD_LENGTH_BYTES / 2);
        for (int i = 0; i < n; i++) {
            passwordBytes[2 * i] = (byte) upperLetters[i];
        }
        return passwordBytes;
    }

    private static byte[] digest(byte[] data, MessageDigest reusableDigest) {
        byte[] full = reusableDigest.digest(data);
        return Arrays.copyOf(full, DIGEST_LENGTH);
    }

    static byte[] rc4(byte[] key, byte[] data) {
        int[] s = new int[256];
        for (int i = 0; i < 256; i++) {
            s[i] = i;
        }
        int j = 0;
        for (int i = 0; i < 256; i++) {
            j = (j + s[i] + (key[i % key.length] & 0xFF)) & 0xFF;
            int tmp = s[i];
            s[i] = s[j];
            s[j] = tmp;
        }
        byte[] out = new byte[data.length];
        int i = 0;
        j = 0;
        for (int k = 0; k < data.length; k++) {
            i = (i + 1) & 0xFF;
            j = (j + s[i]) & 0xFF;
            int tmp = s[i];
            s[i] = s[j];
            s[j] = tmp;
            int ks = s[(s[i] + s[j]) & 0xFF];
            out[k] = (byte) (data[k] ^ ks);
        }
        return out;
    }
}
