package com.mymsm.extract;

import org.junit.jupiter.api.Test;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MsisamPasswordCheckTest {

    // Standard RC4 test vector (widely cited, e.g. Wikipedia's RC4 article):
    // key "Key", plaintext "Plaintext" -> ciphertext BBF316E8D940AF0AD3.
    // Independent of MsisamPasswordCheck's own header-parsing logic, so this
    // catches a broken cipher that a fixture built with the same code would not.
    @Test
    void rc4MatchesKnownTestVector() {
        byte[] key = "Key".getBytes(StandardCharsets.US_ASCII);
        byte[] plaintext = "Plaintext".getBytes(StandardCharsets.US_ASCII);
        byte[] cipher = MsisamPasswordCheck.rc4(key, plaintext);
        assertEquals("BBF316E8D940AF0AD3", toHex(cipher));
    }

    @Test
    void encodeUppercaseLettersIsUtf16LeZeroPadded() {
        byte[] encoded = MsisamPasswordCheck.encodeUppercaseLetters(new char[]{'A', 'B'}, 2);
        assertEquals(40, encoded.length);
        assertArrayEquals(new byte[]{'A', 0, 'B', 0}, java.util.Arrays.copyOf(encoded, 4));
        for (int i = 4; i < encoded.length; i++) {
            assertEquals(0, encoded[i]);
        }
    }

    @Test
    void checkAcceptsMatchingPasswordCaseInsensitively() throws Exception {
        MsisamPasswordCheck.Header header = buildHeaderFor("TESTPASS", false);
        assertTrue(MsisamPasswordCheck.check(header, "testpass"));
        assertTrue(MsisamPasswordCheck.check(header, "TestPass"));
    }

    @Test
    void checkRejectsWrongPassword() throws Exception {
        MsisamPasswordCheck.Header header = buildHeaderFor("TESTPASS", false);
        assertFalse(MsisamPasswordCheck.check(header, "WRONGPASS"));
    }

    @Test
    void checkWorksWithSha1Variant() throws Exception {
        MsisamPasswordCheck.Header header = buildHeaderFor("TESTPASS", true);
        assertTrue(MsisamPasswordCheck.check(header, "testpass"));
        assertFalse(MsisamPasswordCheck.check(header, "other"));
    }

    /**
     * Builds a synthetic header for which {@code password} is the correct
     * password, by running the same digest+RC4 steps forward. Note this
     * shares MsisamPasswordCheck's own primitives, so it validates the
     * header-parsing/comparison wiring, not cipher correctness — that's
     * covered separately by {@link #rc4MatchesKnownTestVector}.
     */
    private static MsisamPasswordCheck.Header buildHeaderFor(String password, boolean useSha1) throws Exception {
        byte[] salt8 = new byte[]{1, 2, 3, 4, 5, 6, 7, 8};
        byte[] baseSalt4 = java.util.Arrays.copyOf(salt8, 4);

        MessageDigest md = MessageDigest.getInstance(useSha1 ? "SHA-1" : "MD5");
        byte[] passwordBytes = new byte[0x28];
        java.nio.ByteBuffer encoded = StandardCharsets.UTF_16LE.encode(password.toUpperCase());
        encoded.get(passwordBytes, 0, Math.min(passwordBytes.length, encoded.remaining()));
        byte[] pwdDigest = java.util.Arrays.copyOf(md.digest(passwordBytes), 0x10);

        byte[] key = new byte[pwdDigest.length + salt8.length];
        System.arraycopy(pwdDigest, 0, key, 0, pwdDigest.length);
        System.arraycopy(salt8, 0, key, pwdDigest.length, salt8.length);

        // RC4 is symmetric (XOR keystream): encrypting baseSalt4 with the
        // correct key is exactly what a real MSISAM header would store, and
        // decrypting it again recovers baseSalt4 only for the same key.
        byte[] encryptedCheck4 = MsisamPasswordCheck.rc4(key, baseSalt4);

        return new MsisamPasswordCheck.Header(salt8, encryptedCheck4, useSha1, true);
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02X", b));
        }
        return sb.toString();
    }
}
