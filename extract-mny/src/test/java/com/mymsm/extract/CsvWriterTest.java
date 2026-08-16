package com.mymsm.extract;

import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.io.StringWriter;
import java.util.Arrays;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CsvWriterTest {

    @Test
    void escapesFieldsContainingComma() {
        assertEquals("\"a,b\"", CsvWriter.escapeField("a,b"));
    }

    @Test
    void escapesFieldsContainingQuotes() {
        assertEquals("\"say \"\"hi\"\"\"", CsvWriter.escapeField("say \"hi\""));
    }

    @Test
    void leavesPlainFieldsUnquoted() {
        assertEquals("plain", CsvWriter.escapeField("plain"));
    }

    @Test
    void nullBecomesEmptyString() {
        assertEquals("", CsvWriter.escapeField(null));
    }

    @Test
    void writeRowJoinsFieldsWithCommaAndNewline() throws IOException {
        StringWriter sw = new StringWriter();
        CsvWriter.writeRow(sw, Arrays.asList("a", "b,c", 3));
        assertEquals("a,\"b,c\",3\n", sw.toString());
    }
}
