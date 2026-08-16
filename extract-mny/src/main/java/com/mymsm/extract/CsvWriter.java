package com.mymsm.extract;

import java.io.IOException;
import java.io.Writer;
import java.util.List;

public final class CsvWriter {

    private CsvWriter() {}

    public static String escapeField(Object value) {
        String s = value == null ? "" : value.toString();
        boolean needsQuoting = s.contains(",") || s.contains("\"") || s.contains("\n") || s.contains("\r");
        if (!needsQuoting) {
            return s;
        }
        return "\"" + s.replace("\"", "\"\"") + "\"";
    }

    public static void writeRow(Writer out, List<Object> fields) throws IOException {
        for (int i = 0; i < fields.size(); i++) {
            if (i > 0) {
                out.write(",");
            }
            out.write(escapeField(fields.get(i)));
        }
        out.write("\n");
    }
}
