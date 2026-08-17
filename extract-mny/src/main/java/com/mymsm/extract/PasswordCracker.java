package com.mymsm.extract;

import com.healthmarketscience.jackcess.Database;
import com.healthmarketscience.jackcess.DatabaseBuilder;
import com.healthmarketscience.jackcess.crypt.CryptCodecProvider;
import com.healthmarketscience.jackcess.crypt.InvalidCredentialsException;

import java.io.File;
import java.io.IOException;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
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
            case "dict":
                requireArgs(args, 3, "dict <file> <wordlist-file>");
                runDict(mnyFile, header, new File(args[2]));
                break;
            case "dictrules":
                requireArgs(args, 3, "dictrules <file> <wordlist-file>");
                try {
                    runDictRules(mnyFile, header, new File(args[2]));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
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
        System.err.println("  dict <file> <wordlist-file>");
        System.err.println("  dictrules <file> <wordlist-file>");
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

    /**
     * Hard cap on distinct candidates ever held in memory for a single
     * {@code near} run. Edit-distance search grows combinatorially with
     * seed length, alphabet size, and distance (roughly
     * (seedLength * 2 * alphabetSize)^distance) - a 19-character seed at
     * distance 3 with a 36-symbol alphabet generates on the order of
     * billions of candidate strings, which is what exhausts heap if they're
     * all materialized at once. Candidates are checked immediately as they
     * are generated (never bulk-collected), and generation stops the
     * instant this cap is hit, so memory stays bounded regardless of how
     * large the theoretical space is.
     */
    private static final int MAX_NEAR_CANDIDATES = 2_000_000;

    private static void runNear(File mnyFile, MsisamPasswordCheck.Header header, String seed, int maxDistance, char[] alphabet) throws IOException {
        MessageDigest md = header.newDigest();
        Set<String> seen = new HashSet<>();
        seen.add(seed);

        long checked = 1;
        if (tryAndConfirm(mnyFile, header, md, seed)) {
            return;
        }

        List<String> frontier = new ArrayList<>();
        frontier.add(seed);
        boolean capped = false;

        for (int d = 1; d <= maxDistance && !capped && !frontier.isEmpty(); d++) {
            List<String> nextFrontier = new ArrayList<>();
            outer:
            for (String s : frontier) {
                for (String variant : editDistanceOneVariants(s, alphabet)) {
                    if (!seen.add(variant)) {
                        continue; // already generated (possibly at an earlier distance)
                    }
                    if (seen.size() > MAX_NEAR_CANDIDATES) {
                        capped = true;
                        break outer;
                    }
                    nextFrontier.add(variant);
                    checked++;
                    if (tryAndConfirm(mnyFile, header, md, variant)) {
                        return;
                    }
                }
            }
            System.out.println("  distance " + d + ": " + checked + " candidates checked");
            frontier = nextFrontier;
        }

        if (capped) {
            System.out.println("Stopped early: candidate space for \"" + seed + "\" exceeded " + MAX_NEAR_CANDIDATES
                    + " distinct strings before reaching distance " + maxDistance + " (checked " + checked + ").");
            System.out.println("This seed is too long/the alphabet too wide for this distance to search exhaustively.");
            System.out.println("Try a shorter seed, a smaller alphabet, or a lower max edit distance for it.");
        } else {
            System.out.println("No match found within edit distance " + maxDistance + " of \"" + seed + "\" (" + checked + " candidates checked).");
        }
    }

    private static boolean tryAndConfirm(File mnyFile, MsisamPasswordCheck.Header header, MessageDigest md, String candidate) throws IOException {
        if (!MsisamPasswordCheck.check(header, candidate, md)) {
            return false;
        }
        System.out.println("Fast checker ACCEPTS: [" + candidate + "]");
        return confirmWithRealLibrary(mnyFile, candidate);
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

    // ---- dict (wordlist attack) -------------------------------------------

    /**
     * Checks each line of a wordlist file as a candidate password, in file
     * order, stopping at the first confirmed hit. Reads and checks one line
     * at a time (never loads the whole file into memory) so this scales to
     * multi-million-line lists like rockyou.txt without the memory blowup
     * {@code near} mode used to have.
     */
    private static void runDict(File mnyFile, MsisamPasswordCheck.Header header, File wordlistFile) throws IOException {
        if (!wordlistFile.isFile()) {
            System.err.println("Not a file: " + wordlistFile);
            System.exit(2);
            return;
        }

        MessageDigest md = header.newDigest();
        long checked = 0;
        long startNanos = System.nanoTime();

        try (java.io.BufferedReader reader = new java.io.BufferedReader(
                new java.io.InputStreamReader(new java.io.FileInputStream(wordlistFile), java.nio.charset.StandardCharsets.ISO_8859_1))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    continue;
                }
                checked++;
                if (tryAndConfirm(mnyFile, header, md, line)) {
                    return;
                }
                if (checked % PROGRESS_INTERVAL == 0) {
                    double elapsed = (System.nanoTime() - startNanos) / 1_000_000_000.0;
                    System.out.printf("  %,d candidates checked, %.0f/sec%n", checked, checked / Math.max(elapsed, 0.001));
                }
            }
        }

        System.out.println("No match found in " + wordlistFile + " (" + checked + " candidates checked).");
    }

    // ---- dictrules (wordlist + common suffix/prefix mutations) -----------

    private static final int DICT_RULES_QUEUE_CAPACITY = 5_000;

    /**
     * Common password-mangling suffixes: digits 0-9, zero-padded 00-99,
     * plausible years, and a handful of common punctuation/number suffixes.
     * Case-mangling rules (a real cracking rule set would include Word,
     * WORD, wOrD, ...) are deliberately omitted - Money's password check
     * uppercases before comparing, so case variants of the same string are
     * redundant here.
     */
    private static List<String> buildRuleSuffixes() {
        Set<String> suffixes = new LinkedHashSet<>();
        suffixes.add("");
        for (int i = 0; i <= 9; i++) {
            suffixes.add(String.valueOf(i));
        }
        for (int i = 0; i <= 99; i++) {
            suffixes.add(String.format("%02d", i));
        }
        for (int year = 1970; year <= 2026; year++) {
            suffixes.add(String.valueOf(year));
        }
        for (String extra : new String[]{"!", "!!", "?", "#", "007", "666", "123", "1234"}) {
            suffixes.add(extra);
        }
        return new ArrayList<>(suffixes);
    }

    private static List<String> mangle(String word, List<String> suffixes) {
        List<String> variants = new ArrayList<>(suffixes.size() + 2);
        for (String suffix : suffixes) {
            variants.add(word + suffix);
        }
        variants.add("1" + word);
        variants.add("0" + word);
        return variants;
    }

    /**
     * Like {@link #runDict} but tries each wordlist entry plus common
     * suffix/prefix mutations ({@link #mangle}), multi-threaded. A single
     * reader thread streams the wordlist file into a small bounded queue
     * (never loading the whole file into memory - same lesson as the {@code
     * near} mode OOM fix) and worker threads consume from it, each
     * generating and checking that word's mutated variants.
     */
    private static void runDictRules(File mnyFile, MsisamPasswordCheck.Header header, File wordlistFile)
            throws IOException, InterruptedException {
        if (!wordlistFile.isFile()) {
            System.err.println("Not a file: " + wordlistFile);
            System.exit(2);
            return;
        }

        List<String> suffixes = buildRuleSuffixes();
        int threads = Runtime.getRuntime().availableProcessors();
        System.out.println("Using " + suffixes.size() + " suffix rules + 2 prefix rules per word ("
                + (suffixes.size() + 2) + " variants/word), " + threads + " threads.");

        BlockingQueue<String> queue = new ArrayBlockingQueue<>(DICT_RULES_QUEUE_CAPACITY);
        String poison = new String("__MNY_DICTRULES_POISON__");
        AtomicBoolean found = new AtomicBoolean(false);
        AtomicReference<String> winner = new AtomicReference<>();
        AtomicLong wordsRead = new AtomicLong();
        AtomicLong candidatesChecked = new AtomicLong();
        long startNanos = System.nanoTime();

        Thread reader = new Thread(() -> {
            try (java.io.BufferedReader r = new java.io.BufferedReader(
                    new java.io.InputStreamReader(new java.io.FileInputStream(wordlistFile),
                            java.nio.charset.StandardCharsets.ISO_8859_1))) {
                String line;
                while ((line = r.readLine()) != null && !found.get()) {
                    if (line.isEmpty()) {
                        continue;
                    }
                    while (!found.get() && !queue.offer(line, 200, java.util.concurrent.TimeUnit.MILLISECONDS)) {
                        // queue full; retry until space frees up or search stops
                    }
                    wordsRead.incrementAndGet();
                }
            } catch (IOException e) {
                e.printStackTrace();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                for (int i = 0; i < threads; i++) {
                    try {
                        queue.put(poison);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }
        });
        reader.start();

        List<Thread> workers = new ArrayList<>();
        for (int t = 0; t < threads; t++) {
            Thread worker = new Thread(() -> {
                MessageDigest md = header.newDigest();
                try {
                    while (!found.get()) {
                        String word = queue.take();
                        if (word == poison) {
                            return;
                        }
                        for (String variant : mangle(word, suffixes)) {
                            if (found.get()) {
                                return;
                            }
                            long c = candidatesChecked.incrementAndGet();
                            if (c % (PROGRESS_INTERVAL * 5) == 0) {
                                double elapsed = (System.nanoTime() - startNanos) / 1_000_000_000.0;
                                System.out.printf("  %,d candidates checked (%,d words read), %.0f/sec%n",
                                        c, wordsRead.get(), c / Math.max(elapsed, 0.001));
                            }
                            try {
                                if (tryAndConfirm(mnyFile, header, md, variant) && found.compareAndSet(false, true)) {
                                    winner.set(variant);
                                    return;
                                }
                            } catch (IOException e) {
                                e.printStackTrace();
                            }
                        }
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers.add(worker);
            worker.start();
        }

        reader.join();
        for (Thread worker : workers) {
            worker.join();
        }

        if (!found.get()) {
            System.out.println("No match found in " + wordlistFile + " with rule mangling ("
                    + candidatesChecked.get() + " candidates checked across " + wordsRead.get() + " words).");
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
