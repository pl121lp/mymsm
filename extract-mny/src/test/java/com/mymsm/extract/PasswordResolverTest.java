package com.mymsm.extract;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class PasswordResolverTest {

    @Test
    void envPasswordTakesPriorityOverConsole() {
        assertEquals("secret", PasswordResolver.resolve("secret", null));
    }

    @Test
    void setButEmptyEnvPasswordIsReturnedAsIs() {
        assertEquals("", PasswordResolver.resolve("", null));
    }

    @Test
    void noEnvAndNoConsoleResolvesToNull() {
        assertNull(PasswordResolver.resolve(null, null));
    }

    @Test
    void fingerprintOfNullPasswordIsNoneMarker() {
        assertEquals("(none)", PasswordResolver.fingerprint(null));
    }

    @Test
    void fingerprintIsStableForSameInput() {
        assertEquals(PasswordResolver.fingerprint("hunter2"), PasswordResolver.fingerprint("hunter2"));
    }

    @Test
    void fingerprintDiffersForDifferentInput() {
        assertNotEquals(PasswordResolver.fingerprint("hunter2"), PasswordResolver.fingerprint("hunter3"));
    }
}
