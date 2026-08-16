package com.mymsm.extract;

import com.healthmarketscience.jackcess.crypt.CryptCodecProvider;
import com.healthmarketscience.jackcess.Database;
import com.healthmarketscience.jackcess.DatabaseBuilder;
import com.healthmarketscience.jackcess.Column;
import com.healthmarketscience.jackcess.Table;

import java.io.BufferedWriter;
import java.io.Console;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class Main {

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: extract-mny <input.mny> <output_dir>");
            System.exit(2);
            return;
        }
        File input = new File(args[0]);
        File outputDir = new File(args[1]);
        if (!outputDir.exists() && !outputDir.mkdirs()) {
            throw new IOException("Could not create output directory: " + outputDir);
        }

        String password = resolvePassword();
        try (Database db = new DatabaseBuilder(input)
                .setReadOnly(true)
                .setCodecProvider(new CryptCodecProvider(password))
                .open()) {

            File manifestFile = new File(outputDir, "manifest.csv");
            try (Writer manifest = new BufferedWriter(new FileWriter(manifestFile, StandardCharsets.UTF_8))) {
                List<Object> header = new ArrayList<>();
                header.add("table");
                header.add("row_count");
                header.add("column_name");
                header.add("column_type");
                CsvWriter.writeRow(manifest, header);

                for (String tableName : db.getTableNames()) {
                    Table table = db.getTable(tableName);
                    int rowCount = dumpTable(table, tableName, outputDir);
                    for (Column column : table.getColumns()) {
                        List<Object> manifestRow = new ArrayList<>();
                        manifestRow.add(tableName);
                        manifestRow.add(rowCount);
                        manifestRow.add(column.getName());
                        manifestRow.add(column.getType().toString());
                        CsvWriter.writeRow(manifest, manifestRow);
                    }
                    System.out.println("Dumped " + tableName + ": " + rowCount + " rows");
                }
            }
        }
    }

    /**
     * Resolves the Money file password, if any, in priority order:
     * 1. The {@code MNY_PASSWORD} environment variable, if set (including set-but-empty).
     * 2. An interactive prompt via {@link System#console()}, if a console is attached.
     * 3. {@code null} (no password), if neither of the above is available.
     */
    private static String resolvePassword() {
        String envPassword = System.getenv("MNY_PASSWORD");
        if (envPassword != null) {
            return envPassword;
        }
        Console console = System.console();
        if (console != null) {
            char[] chars = console.readPassword("Money file password (leave blank if none): ");
            if (chars != null) {
                return new String(chars);
            }
        }
        return null;
    }

    private static int dumpTable(Table table, String tableName, File outputDir) throws IOException {
        List<String> columnNames = new ArrayList<>();
        for (Column column : table.getColumns()) {
            columnNames.add(column.getName());
        }

        File tableFile = new File(outputDir, tableName + ".csv");
        int rowCount = 0;
        try (Writer out = new BufferedWriter(new FileWriter(tableFile, StandardCharsets.UTF_8))) {
            List<Object> header = new ArrayList<>(columnNames);
            CsvWriter.writeRow(out, header);
            for (Map<String, Object> row : table) {
                List<Object> values = new ArrayList<>();
                for (String columnName : columnNames) {
                    values.add(row.get(columnName));
                }
                CsvWriter.writeRow(out, values);
                rowCount++;
            }
        }
        return rowCount;
    }
}
