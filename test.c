#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Forward declaration of the vector structure
typedef struct Vector Vector;

// Define function pointer types for vector operations
typedef void (*FreeFunc)(void* data);
typedef int (*CompareFunc)(const void* a, const void* b);

struct Vector {
    void** items;       // Array of generic (void*) pointers
    int capacity;       // Total allocated slots
    int total;          // Number of items currently stored
    
    // "Methods" attached to individual vector instances
    void (*add)(Vector*, void*);
    void* (*get)(Vector*, int);
    void (*sort)(Vector*, CompareFunc);
    void (*free)(Vector*, FreeFunc);
};

// --- Private Helper Functions ---

// Handles dynamic resizing when the vector is full
static void vector_resize(Vector* v, int capacity) {
    void** items = realloc(v->items, sizeof(void*) * capacity);
    if (items) {
        v->items = items;
        v->capacity = capacity;
    }
}

// --- Public Methods ---

// Appends an element and expands memory exponentially if full
static void vector_add(Vector* v, void* item) {
    if (v->capacity == v->total) {
        vector_resize(v, v->capacity * 2);
    }
    v->items[v->total++] = item;
}

// Retrieves an element by index with basic bounds checking
static void* vector_get(Vector* v, int index) {
    if (index >= 0 && index < v->total) {
        return v->items[index];
    }
    return NULL;
}

// Sorts the vector using standard library qsort and a custom callback
static void vector_sort(Vector* v, CompareFunc comp) {
    if (v->items && v->total > 0) {
        qsort(v->items, v->total, sizeof(void*), comp);
    }
}

// Cleans up internal pointer allocations and individual elements
static void vector_free(Vector* v, FreeFunc free_item) {
    if (!v) return;
    
    if (free_item) {
        for (int i = 0; i < v->total; i++) {
            free_item(v->items[i]);
        }
    }
    free(v->items);
    free(v);
}

// --- Constructor ---

// Allocates and initializes the pseudo-object
Vector* create_vector(int initial_capacity) {
    Vector* v = malloc(sizeof(Vector));
    if (!v) return NULL;

    v->capacity = initial_capacity > 0 ? initial_capacity : 4;
    v->total = 0;
    v->items = malloc(sizeof(void*) * v->capacity);
    
    // Assign method pointers
    v->add = vector_add;
    v->get = vector_get;
    v->sort = vector_sort;
    v->free = vector_free;
    
    return v;
}

// --- Application Code ---

// Custom structure to hold inside our generic vector
typedef struct {
    char name[32];
    int score;
} Player;

// Callback function to compare players by score (for sorting)
int compare_players(const void* a, const void* b) {
    // qsort passes pointers to the elements; since elements are void*, we get void**
    const Player* playerA = *(const Player**)a;
    const Player* playerB = *(const Player**)b;
    return playerB->score - playerA->score; // Descending order
}

int main() {
    // 1. Instantiate the vector with a small initial capacity (forces resizing)
    Vector* player_list = create_vector(2);

    // 2. Dynamically allocate data elements
    Player* p1 = malloc(sizeof(Player));
    strcpy(p1->name, "Alice"); p1->score = 95;

    Player* p2 = malloc(sizeof(Player));
    strcpy(p2->name, "Bob"); p2->score = 88;

    Player* p3 = malloc(sizeof(Player));
    strcpy(p3->name, "Charlie"); p3->score = 99;

    // 3. Utilize object-style syntax to populate vector
    player_list->add(player_list, p1);
    player_list->add(player_list, p2);
    player_list->add(player_list, p3);

    // 4. Sort using the custom comparison callback
    player_list->sort(player_list, compare_players);

    // 5. Display results
    printf("Leaderboard:\n");
    for (int i = 0; i < player_list->total; i++) {
        Player* p = (Player*)player_list->get(player_list, i);
        printf("%d. %s - %d\n", i + 1, p->name, p->score);
    }

    // 6. Free everything (Pass standard free() to clean up each Player struct)
    player_list->free(player_list, free);

    return 0;
}