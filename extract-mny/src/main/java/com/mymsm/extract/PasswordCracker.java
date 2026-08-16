package com.mymsm.extract;

import com.healthmarketscience.jackcess.Database;
import com.healthmarketscience.jackcess.DatabaseBuilder;
import com.healthmarketscience.jackcess.crypt.CryptCodecProvider;
import com.healthmarketscience.jackcess.crypt.InvalidCredentialsException;

import java.io.File;
import java.io.IOException;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Offline password search for a Money (.mny) file, using {@link
 * MsisamPasswordCheck} instead of opening the file through jackcess for
 * every candidate. Any candidate the fast checker accepts is re-verified
 * against the real jackcess-encrypt library before being reported as a hit
 * — {@link MsisamPasswordCheck}'s 4-byte check has a 1-in-4-billion false
 * positive rate per wrong guess, negligible for one password but not for
 * billions of brute-force attempts, so this closes the loop with the
 * authoritative implementation.
 *
 * Modes:
 * <pre>
 *   verify &lt;file&gt; &lt;password&gt;                 - check a single candidate
 *   benchmark &lt;file&gt; [seconds]                - measure attempts/sec on this machine
 *   near &lt;file&gt; &lt;seed&gt; [maxEditDistance]      - try edit-distance mutations of a seed
 *   bruteforce &lt;file&gt; &lt;length&gt; [alphabet]     - exhaustively try every combination
 * </pre>
 */
public final class PasswordCracker {

    private static final String DEFAULT_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    private static final long PROGRESS_INTERVAL = 2_000_000L;

    public static void main(String[] args) throws IOException {
        if (args.length < 2) {
            printUsage();
            System.exit(2);
            return;
        }

        String mode = args[0];
        File mnyFile = new File(args[1]);
        if (!mnyFile.isFile()) {
            System.err.println("Not a file: " + mnyFile);
            System.exit(2);
            return;
        }

        MsisamPasswordCheck.Header header = MsisamPasswordCheck.readHeader(mnyFile);
        if (!header.newEncryption) {
            System.out.println("WARNING: this file uses the old MSISAM encoding scheme, which this tool");
            System.out.println("does not implement (it doesn't use a password hash at all). Results below");
            System.out.println("are not meaningful for this file.");
        }

        switch (mode) {
            case "verify":
                requireArgs(args, 3, "verify <file> <password>");
                runVerify(mnyFile, header, args[2]);
                break;
            case "benchmark":
                int seconds = args.length > 2 ? Integer.parseInt(args[2]) : 5;
                runBenchmark(header, seconds);
                break;
            case "near":
                requireArgs(args, 3, "near <file> <seed> [maxEditDistance] [mutationAlphabet]");
                int maxDistance = args.length > 3 ? Integer.parseInt(args[3]) : 2;
                char[] nearAlphabet = args.length > 4 ? args[4].toCharArray() : LOWER_ALPHABET;
                runNear(mnyFile, header, args[2], maxDistance, nearAlphabet);
                break;
            case "bruteforce":
                requireArgs(args, 3, "bruteforce <file> <length> [alphabet]");
                int length = Integer.parseInt(args[2]);
                String alphabet = args.length > 3 ? args[3].toUpperCase() : DEFAULT_ALPHABET;
                runBruteforce(mnyFile, header, length, alphabet);
                break;
            default:
                printUsage();
                System.exit(2);
        }
    }

    private static void requireArgs(String[] args, int min, String usage) {
        if (args.length < min) {
            System.err.println("Usage: PasswordCracker " + usage);
            System.exit(2);
        }
    }

    private static void printUsage() {
        System.err.println("Usage: PasswordCracker <mode> <file.mny> [args...]");
        System.err.println("  verify <file> <password>");
        System.err.println("  benchmark <file> [seconds]");
        System.err.println("  near <file> <seed> [maxEditDistance] [mutationAlphabet]");
        System.err.println("  bruteforce <file> <length> [alphabet]");
    }

    // ---- verify --------------------------------------------------------

    private static void runVerify(File mnyFile, MsisamPasswordCheck.Header header, String candidate) throws IOException {
        boolean fastResult = MsisamPasswordCheck.check(header, candidate);
        System.out.println("Fast checker: " + (fastResult ? "ACCEPTS" : "rejects") + " [" + candidate + "]");
        if (fastResult) {
            confirmWithRealLibrary(mnyFile, candidate);
        }
    }

    // ---- benchmark -------------------------------------------------------

    private static void runBenchmark(MsisamPasswordCheck.Header header, int seconds) {
        System.out.println("Benchmarking for " + seconds + "s on " + Runtime.getRuntime().availableProcessors() + " threads...");
        int threads = Runtime.getRuntime().availableProcessors();
        AtomicLong totalAttempts = new AtomicLong();
        long deadline = System.nanoTime() + seconds * 1_000_000_000L;

        List<Thread> workers = new ArrayList<>();
        for (int t = 0; t < threads; t++) {
            Thread worker = new Thread(() -> {
                MessageDigest md = header.newDigest();
                char[] candidate = new char[8];
                long localAttempts = 0;
                long counter = 0;
                while (System.nanoTime() < deadline) {
                    for (int i = 0; i < 8; i++) {
                        candidate[i] = DEFAULT_ALPHABET.charAt((int) ((counter >> (i * 5)) % 26));
                    }
                    counter++;
                    byte[] encoded = MsisamPasswordCheck.encodeUppercaseLetters(candidate, 8);
                    MsisamPasswordCheck.checkEncodedPassword(header, encoded, md);
                    localAttempts++;
                }
                totalAttempts.addAndGet(localAttempts);
            });
            workers.add(worker);
            worker.start();
        }
        workers.forEach(PasswordCracker::joinUninterruptibly);

        double rate = totalAttempts.get() / (double) seconds;
        System.out.printf("Measured: %.0f checks/sec (%,d total, %d threads)%n", rate, totalAttempts.get(), threads);
        printEta(rate);
    }

    private static void printEta(double ratePerSecond) {
        double space = Math.pow(26, 8);
        double secondsToExhaust = space / ratePerSecond;
        System.out.printf("26^8 = %.3e combinations -> exhaustive search would take ~%s at this rate%n",
                space, formatDuration(secondsToExhaust));
    }

    private static String formatDuration(double seconds) {
        double minutes = seconds / 60;
        double hours = minutes / 60;
        double days = hours / 24;
        double years = days / 365.25;
        if (years >= 1) {
            return String.format("%.1f years", years);
        }
        if (days >= 1) {
            return String.format("%.1f days", days);
        }
        if (hours >= 1) {
            return String.format("%.1f hours", hours);
        }
        if (minutes >= 1) {
            return String.format("%.1f minutes", minutes);
        }
        return String.format("%.1f seconds", seconds);
    }

    // ---- near (edit-distance mutations of a seed) -----------------------

    private static void runNear(File mnyFile, MsisamPasswordCheck.Header header, String seed, int maxDistance, char[] alphabet) throws IOException {
        Set<String> candidates = new LinkedHashSet<>();
        candidates.add(seed);
        Set<String> frontier = new LinkedHashSet<>(candidates);
        for (int d = 1; d <= maxDistance; d++) {
            Set<String> next = new LinkedHashSet<>();
            for (String s : frontier) {
                next.addAll(editDistanceOneVariants(s, alphabet));
            }
            next.removeAll(candidates);
            candidates.addAll(next);
            frontier = next;
        }

        System.out.println("Trying " + candidates.size() + " candidates within edit distance " + maxDistance + " of \"" + seed + "\"...");
        MessageDigest md = header.newDigest();
        for (String candidate : candidates) {
            if (MsisamPasswordCheck.check(header, candidate, md)) {
                System.out.println("Fast checker ACCEPTS: [" + candidate + "]");
                if (confirmWithRealLibrary(mnyFile, candidate)) {
                    return;
                }
            }
        }
        System.out.println("No match found within edit distance " + maxDistance + " of \"" + seed + "\".");
    }

    private static final char[] LOWER_ALPHABET = "abcdefghijklmnopqrstuvwxyz".toCharArray();

    private static List<String> editDistanceOneVariants(String s, char[] alphabet) {
        List<String> out = new ArrayList<>();
        int n = s.length();

        // deletions
        for (int i = 0; i < n; i++) {
            out.add(s.substring(0, i) + s.substring(i + 1));
        }
        // substitutions
        for (int i = 0; i < n; i++) {
            for (char c : alphabet) {
                if (c != Character.toLowerCase(s.charAt(i))) {
                    out.add(s.substring(0, i) + c + s.substring(i + 1));
                }
            }
        }
        // insertions
        for (int i = 0; i <= n; i++) {
            for (char c : alphabet) {
                out.add(s.substring(0, i) + c + s.substring(i));
            }
        }
        // adjacent transpositions
        for (int i = 0; i < n - 1; i++) {
            StringBuilder sb = new StringBuilder(s);
            char tmp = sb.charAt(i);
            sb.setCharAt(i, sb.charAt(i + 1));
            sb.setCharAt(i + 1, tmp);
            out.add(sb.toString());
        }
        return out;
    }

    // ---- bruteforce ------------------------------------------------------

    private static void runBruteforce(File mnyFile, MsisamPasswordCheck.Header header, int length, String alphabet) throws IOException {
        char[] symbols = alphabet.toCharArray();
        double space = Math.pow(symbols.length, length);
        int threads = Runtime.getRuntime().availableProcessors();
        System.out.printf("Searching %s^%d = %.3e combinations with %d threads...%n", alphabet, length, space, threads);

        AtomicBoolean found = new AtomicBoolean(false);
        AtomicReference<String> winner = new AtomicReference<>();
        AtomicLong totalAttempts = new AtomicLong();
        long startNanos = System.nanoTime();

        List<Thread> workers = new ArrayList<>();
        for (int t = 0; t < threads; t++) {
            long startIndex = t;
            long stride = threads;
            workers.add(new Thread(() -> searchRange(header, symbols, length, startIndex, stride, found, winner, totalAttempts, startNanos)));
        }
        workers.forEach(Thread::start);
        workers.forEach(PasswordCracker::joinUninterruptibly);

        if (found.get()) {
            String candidate = winner.get();
            System.out.println("Fast checker ACCEPTS: [" + candidate + "]");
            confirmWithRealLibrary(mnyFile, candidate);
        } else {
            System.out.println("Exhausted search space, no match found.");
        }
    }

    private static void searchRange(MsisamPasswordCheck.Header header, char[] symbols, int length,
                                     long startIndex, long stride, AtomicBoolean found,
                                     AtomicReference<String> winner, AtomicLong totalAttempts, long startNanos) {
        MessageDigest md = header.newDigest();
        char[] candidate = new char[length];
        long base = symbols.length;
        long index = startIndex;
        long localAttempts = 0;
        while (!found.get()) {
            long remaining = index;
            for (int i = length - 1; i >= 0; i--) {
                candidate[i] = symbols[(int) (remaining % base)];
                remaining /= base;
            }
            if (remaining != 0) {
                return; // index overflowed the space for this length; this thread's range is exhausted
            }

            byte[] encoded = MsisamPasswordCheck.encodeUppercaseLetters(candidate, length);
            if (MsisamPasswordCheck.checkEncodedPassword(header, encoded, md)) {
                if (found.compareAndSet(false, true)) {
                    winner.set(new String(candidate));
                }
                return;
            }

            localAttempts++;
            if (localAttempts % PROGRESS_INTERVAL == 0) {
                long total = totalAttempts.addAndGet(PROGRESS_INTERVAL);
                double elapsed = (System.nanoTime() - startNanos) / 1_000_000_000.0;
                System.out.printf("  %,d attempts, %.0f/sec%n", total, total / Math.max(elapsed, 0.001));
            }

            index += stride;
        }
    }

    // ---- shared confirmation step ----------------------------------------

    /**
     * Re-checks a fast-checker hit through the real jackcess-encrypt
     * library, since that's the code that will actually be used to extract
     * data and is the authoritative answer.
     */
    private static boolean confirmWithRealLibrary(File mnyFile, String candidate) throws IOException {
        try (Database db = new DatabaseBuilder(mnyFile)
                .setReadOnly(true)
                .setCodecProvider(new CryptCodecProvider(candidate))
                .open()) {
            System.out.println("CONFIRMED via jackcess-encrypt: password is [" + candidate + "] (" + db.getTableNames().size() + " tables).");
            return true;
        } catch (InvalidCredentialsException e) {
            System.out.println("Fast checker false positive (this shouldn't happen) - jackcess-encrypt rejected [" + candidate + "]. Continuing search.");
            return false;
        }
    }

    private static void joinUninterruptibly(Thread t) {
        try {
            t.join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
