// hm_stress.fx - HashMap / HashMapInt Stress Test
//
// Tests:
//   1. Basic set/get/has/remove on HashMap (string keys)
//   2. Basic set/get/has/remove on HashMapInt (u64 keys)
//   3. Overwrite existing keys
//   4. Large insertion forcing multiple resizes
//   5. Remove all entries, verify count reaches 0
//   6. Re-insert after full clear
//   7. Collision/probe stress: sequential integer keys

#import "standard.fx", "collections.fx";

using standard::io::console,
      standard::collections;

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

int g_pass = 0;
int g_fail = 0;

def pass(noopstr name) -> void
{
    print("  [PASS] \0");
    print(name);
    print();
    g_pass = g_pass + 1;
};

def fail(noopstr name) -> void
{
    print("  [FAIL] \0");
    print(name);
    print();
    g_fail = g_fail + 1;
};

def check(bool cond, noopstr name) -> void
{
    if (cond)
    {
        pass(name);
    }
    else
    {
        fail(name);
    };
};

// -------------------------------------------------------------------------
// Section 1 - HashMap basic operations
// -------------------------------------------------------------------------

def test_hm_basic() -> void
{
    print("--- HashMap basic ---\0");
    print();

    HashMap m(16);
    defer m.__exit();

    // Insert three entries
    m.hm_set("alpha\0",   (void*)1);
    m.hm_set("beta\0",    (void*)2);
    m.hm_set("gamma\0",   (void*)3);

    check(m.hm_count() == 3,        "count == 3 after 3 inserts\0");
    check(m.hm_has("alpha\0"),       "has alpha\0");
    check(m.hm_has("beta\0"),        "has beta\0");
    check(m.hm_has("gamma\0"),       "has gamma\0");
    check(!m.hm_has("delta\0"),      "not has delta\0");

    check(m.hm_get("alpha\0") == (void*)1, "get alpha == 1\0");
    check(m.hm_get("beta\0")  == (void*)2, "get beta == 2\0");
    check(m.hm_get("gamma\0") == (void*)3, "get gamma == 3\0");
    check(m.hm_get("delta\0") == (void*)0, "get delta == NULL\0");

    // Overwrite
    m.hm_set("beta\0", (void*)99);
    check(m.hm_get("beta\0") == (void*)99, "overwrite beta -> 99\0");
    check(m.hm_count() == 3,               "count still 3 after overwrite\0");

    // Remove
    check(m.hm_remove("alpha\0"),  "remove alpha returns true\0");
    check(!m.hm_has("alpha\0"),    "alpha gone after remove\0");
    check(m.hm_count() == 2,       "count == 2 after remove\0");

    check(!m.hm_remove("alpha\0"), "remove alpha again returns false\0");
    check(m.hm_count() == 2,       "count unchanged after double remove\0");
};

// -------------------------------------------------------------------------
// Section 2 - HashMapInt basic operations
// -------------------------------------------------------------------------

def test_hmi_basic() -> void
{
    print("--- HashMapInt basic ---\0");
    print();

    HashMapInt m(16);
    defer m.__exit();

    m.hmi_set(100u, (void*)10);
    m.hmi_set(200u, (void*)20);
    m.hmi_set(300u, (void*)30);

    check(m.hmi_count() == 3,          "count == 3 after 3 inserts\0");
    check(m.hmi_has(100u),             "has 100\0");
    check(m.hmi_has(200u),             "has 200\0");
    check(m.hmi_has(300u),             "has 300\0");
    check(!m.hmi_has(400u),            "not has 400\0");

    check(m.hmi_get(100u) == (void*)10, "get 100 == 10\0");
    check(m.hmi_get(200u) == (void*)20, "get 200 == 20\0");
    check(m.hmi_get(300u) == (void*)30, "get 300 == 30\0");
    check(m.hmi_get(400u) == (void*)0,  "get 400 == NULL\0");

    // Overwrite
    m.hmi_set(200u, (void*)77);
    check(m.hmi_get(200u) == (void*)77, "overwrite 200 -> 77\0");
    check(m.hmi_count() == 3,           "count still 3 after overwrite\0");

    // Remove
    check(m.hmi_remove(100u),  "remove 100 returns true\0");
    check(!m.hmi_has(100u),    "100 gone after remove\0");
    check(m.hmi_count() == 2,  "count == 2 after remove\0");

    check(!m.hmi_remove(100u), "remove 100 again returns false\0");
};

// -------------------------------------------------------------------------
// Section 3 - Resize stress (HashMap)
// Inserts N entries, forcing several doublings, then verifies all survive.
// -------------------------------------------------------------------------

def test_hm_resize() -> void
{
    print("--- HashMap resize stress ---\0");
    print();

    HashMap m(16);
    defer m.__exit();

    // Insert 200 entries with keys "key_000" .. "key_199"
    int n = 200, i,
        ones, tens, hundreds;
    byte[16] kbuf;
    void* v;

    while (i < n)
    {
        // Build key string "key_NNN\0"
        kbuf[0] = 107; // k
        kbuf[1] = 101; // e
        kbuf[2] = 121; // y
        kbuf[3] = 95;  // _
        hundreds = i / 100;
        tens     = (i % 100) / 10;
        ones     = i % 10;
        kbuf[4] = (byte)(48 + hundreds);
        kbuf[5] = (byte)(48 + tens);
        kbuf[6] = (byte)(48 + ones);
        kbuf[7] = 0;
        m.hm_set(@kbuf, (void*)i);
        i = i + 1;
    };

    check(m.hm_count() == 200, "count == 200 after bulk insert\0");

    // Verify all 200 retrievable
    bool all_found = true;
    i = 0;
    while (i < n)
    {
        kbuf[0] = 107;
        kbuf[1] = 101;
        kbuf[2] = 121;
        kbuf[3] = 95;
        hundreds = i / 100;
        tens     = (i % 100) / 10;
        ones     = i % 10;
        kbuf[4] = (byte)(48 + hundreds);
        kbuf[5] = (byte)(48 + tens);
        kbuf[6] = (byte)(48 + ones);
        kbuf[7] = 0;
        v = m.hm_get(@kbuf);
        if (v != (void*)i)
        {
            all_found = false;
        };
        i = i + 1;
    };
    check(all_found, "all 200 entries correct after resize\0");

    // Capacity should have grown past 16
    check(m.hm_capacity() > 16, "capacity grew beyond initial 16\0");
};

// -------------------------------------------------------------------------
// Section 4 - Resize stress (HashMapInt)
// -------------------------------------------------------------------------

def test_hmi_resize() -> void
{
    print("--- HashMapInt resize stress ---\0");
    print();

    HashMapInt m(16);
    defer m.__exit();

    int n = 500, i;
    void* v;

    while (i < n)
    {
        m.hmi_set((u64)i, (void*)i);
        i = i + 1;
    };

    check(m.hmi_count() == 500, "count == 500 after bulk insert\0");

    bool all_found = true;
    i = 0;
    while (i < n)
    {
        v = m.hmi_get((u64)i);
        if (v != (void*)i)
        {
            all_found = false;
        };
        i = i + 1;
    };
    check(all_found, "all 500 entries correct after resize\0");
    check(m.hmi_capacity() > 16, "capacity grew beyond initial 16\0");
};

// -------------------------------------------------------------------------
// Section 5 - Remove all, re-insert (HashMap)
// -------------------------------------------------------------------------

def test_hm_clear_reinsert() -> void
{
    print("--- HashMap clear + re-insert ---\0");
    print();

    HashMap m(16);
    defer m.__exit();

    m.hm_set("one\0",   (void*)1);
    m.hm_set("two\0",   (void*)2);
    m.hm_set("three\0", (void*)3);

    m.hm_remove("one\0");
    m.hm_remove("two\0");
    m.hm_remove("three\0");

    check(m.hm_count() == 0, "count == 0 after removing all\0");

    m.hm_set("one\0", (void*)11);
    check(m.hm_count() == 1,                   "count == 1 after re-insert\0");
    check(m.hm_get("one\0") == (void*)11,      "re-inserted value correct\0");
    check(m.hm_get("two\0") == (void*)0,       "two still absent\0");
};

// -------------------------------------------------------------------------
// Section 6 - Remove all, re-insert (HashMapInt)
// -------------------------------------------------------------------------

def test_hmi_clear_reinsert() -> void
{
    print("--- HashMapInt clear + re-insert ---\0");
    print();

    HashMapInt m(16);
    defer m.__exit();

    m.hmi_set(1u, (void*)10);
    m.hmi_set(2u, (void*)20);
    m.hmi_set(3u, (void*)30);

    m.hmi_remove(1u);
    m.hmi_remove(2u);
    m.hmi_remove(3u);

    check(m.hmi_count() == 0, "count == 0 after removing all\0");

    m.hmi_set(1u, (void*)99);
    check(m.hmi_count() == 1,              "count == 1 after re-insert\0");
    check(m.hmi_get(1u) == (void*)99,     "re-inserted value correct\0");
    check(m.hmi_get(2u) == (void*)0,      "2 still absent\0");
};

// -------------------------------------------------------------------------
// Section 7 - Interleaved insert/remove (HashMap)
// Insert 100, remove every other one, verify survivors.
// -------------------------------------------------------------------------

def test_hm_interleaved() -> void
{
    print("--- HashMap interleaved insert/remove ---\0");
    print();

    HashMap m(32);
    defer m.__exit();

    byte[16] kbuf;
    void* v;
    int n = 100, i,
        ones, tens, hundreds;

    // Insert 0..99
    while (i < n)
    {
        hundreds = i / 100;
        tens     = (i % 100) / 10;
        ones     = i % 10;
        kbuf[0] = (byte)(48 + hundreds);
        kbuf[1] = (byte)(48 + tens);
        kbuf[2] = (byte)(48 + ones);
        kbuf[3] = 0;
        m.hm_set(@kbuf, (void*)i);
        i = i + 1;
    };

    // Remove even indices
    i = 0;
    while (i < n)
    {
        if (i % 2 == 0)
        {
            hundreds = i / 100;
            tens     = (i % 100) / 10;
            ones     = i % 10;
            kbuf[0] = (byte)(48 + hundreds);
            kbuf[1] = (byte)(48 + tens);
            kbuf[2] = (byte)(48 + ones);
            kbuf[3] = 0;
            m.hm_remove(@kbuf);
        };
        i = i + 1;
    };

    check(m.hm_count() == 50, "count == 50 after removing evens\0");

    // Odd indices must still be present with correct values
    bool odds_ok = true;
    i = 1;
    while (i < n)
    {
        hundreds = i / 100;
        tens     = (i % 100) / 10;
        ones     = i % 10;
        kbuf[0] = (byte)(48 + hundreds);
        kbuf[1] = (byte)(48 + tens);
        kbuf[2] = (byte)(48 + ones);
        kbuf[3] = 0;
        v = m.hm_get(@kbuf);
        if (v != (void*)i)
        {
            odds_ok = false;
        };
        i = i + 2;
    };
    check(odds_ok, "all odd entries survive and correct\0");

    // Even indices must be absent
    bool evens_gone = true;
    i = 0;
    while (i < n)
    {
        hundreds = i / 100;
        tens     = (i % 100) / 10;
        ones     = i % 10;
        kbuf[0] = (byte)(48 + hundreds);
        kbuf[1] = (byte)(48 + tens);
        kbuf[2] = (byte)(48 + ones);
        kbuf[3] = 0;
        if (m.hm_has(@kbuf))
        {
            evens_gone = false;
        };
        i = i + 2;
    };
    check(evens_gone, "all even entries absent\0");
};

// -------------------------------------------------------------------------
// main
// -------------------------------------------------------------------------

def main() -> int
{
    print("==============================\0");
    print();
    print("  HashMap Stress Test\0");
    print();
    print("==============================\0");
    print();

    test_hm_basic();
    test_hmi_basic();
    test_hm_resize();
    test_hmi_resize();
    test_hm_clear_reinsert();
    test_hmi_clear_reinsert();
    test_hm_interleaved();

    print("==============================\0");
    print();
    print("Results: \0");
    print(g_pass);
    print(" passed, \0");
    print(g_fail);
    print(" failed\0");
    print();
    print("==============================\0");
    print();

    if (g_fail != 0)
    {
        return 1;
    };
    return 0;
};
