package com.mymsm.extract;

import java.io.Console;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Resolves the Money file password, if any, in priority order:
 * 1. The {@code MNY_PASSWORD} environment variable, if set (including set-but-empty).
 * 2. An interactive prompt via {@link System#console()}, if a console is attached.
 * 3. {@code null} (no password), if neither of the above is available.
 *
 * Shared by {@link Main} and the {@code PasswordDiag} tool so both resolve a
 * password identically.
 */
public final class PasswordResolver {

    private PasswordResolver() {
    }

    public static String resolve() {
        return resolve(System.getenv("MNY_PASSWORD"), System.console());
    }

    static String resolve(String envPassword, Console console) {
        if (envPassword != null) {
            return envPassword;
        }
        if (console != null) {
            char[] chars = console.readPassword("Money file password (leave blank if none): ");
            if (chars != null) {
                return new String(chars);
            }
        }
        return null;
    }

    /**
     * A short, non-reversible fingerprint for comparing whether two resolved
     * passwords are the same string, without ever printing the password itself.
     */
    public static String fingerprint(String password) {
        if (password == null) {
            return "(none)";
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(password.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : hash) {
                hex.append(String.format("%02x", b));
            }
            return hex.substring(0, 12);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
