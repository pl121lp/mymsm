package com.mymsm.extract;

import com.healthmarketscience.jackcess.crypt.CryptCodecProvider;
import com.healthmarketscience.jackcess.crypt.InvalidCredentialsException;
import com.healthmarketscience.jackcess.Database;
import com.healthmarketscience.jackcess.DatabaseBuilder;

import java.io.File;
import java.io.IOException;

/**
 * Standalone tool for diagnosing "Incorrect password" failures against a
 * Money (.mny) file, without running the full extraction pipeline.
 *
 * Resolves the password exactly like {@link Main} does (same {@link
 * PasswordResolver}), reports its length and a non-reversible fingerprint —
 * so a password can be compared across two runs (e.g. env var vs.
 * interactive prompt) without ever printing it — then attempts to open the
 * file and reports whether the password was accepted.
 */
public final class PasswordDiag {

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: PasswordDiag <input.mny>");
            System.exit(2);
            return;
        }

        File input = new File(args[0]);
        if (!input.isFile()) {
            System.err.println("Not a file: " + input);
            System.exit(2);
            return;
        }

        String password = PasswordResolver.resolve();
        if (password == null) {
            System.out.println("Resolved password: (none)");
        } else {
            System.out.println("Resolved password: length=" + password.length()
                    + ", fingerprint=" + PasswordResolver.fingerprint(password));
        }
        System.out.println("Password fed to the decryption step: [" + password + "]");

        try (Database db = new DatabaseBuilder(input)
                .setReadOnly(true)
                .setCodecProvider(new CryptCodecProvider(password))
                .open()) {
            int tableCount = db.getTableNames().size();
            System.out.println("SUCCESS: opened " + input.getName() + " (" + tableCount + " tables). Password is correct.");
        } catch (InvalidCredentialsException e) {
            System.out.println("FAILED: the password above was rejected by the file (InvalidCredentialsException).");
            System.out.println("The length/fingerprint shown is what actually reached the decryption step —");
            System.out.println("run this tool twice (once via MNY_PASSWORD, once at the interactive prompt) and");
            System.out.println("compare the fingerprints. A mismatch means shell quoting, a stray character, or");
            System.out.println("a typo changed the password before Java ever saw it — not that the library is wrong.");
            System.exit(1);
        } catch (IOException e) {
            System.out.println("FAILED: could not open " + input.getName() + " as a Money/Access database: " + e.getMessage());
            System.out.println("Check that this is the actual .mny file, not a .mbf backup archive (a different format).");
            System.exit(1);
        }
    }
}
