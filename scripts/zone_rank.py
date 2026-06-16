"""
Custom MinHeap Algorithm — Top K Busiest Pickup Zones

Implements a min-heap data structure  to identify the K busiest NYC taxi pickup zones.

Algorithm  : Top-K Selection using Min-Heap
Time complexity : O(n log k) — n = total zones, k = top zones to be found
Space complexity : O(k)— only K items stored in heap.

Why MinHeap is better than sorting all zones:
- Sorting all zones use O(n log n)
- MinHeap approach is  O(n log k) which is faster k << n
- For k=15 and n=263 zones: ~1052 operations vs ~2104 for full sort
- Heap only keeps 15 items in memory — sort keeps all 263

Pseudo-code:
    1. Create empty min-heap of size k
    2. Query database for trip count per pickup zone
    3. For each zone:
         a. If heap not full — insert zone and bubble up
         b. If zone count > heap minimum — replace minimum and bubble down
    4. Extract all K items from heap
    5. Sort descending using manual bubble sort
    6. Return ranked list from busiest to least busy
"""
import sqlite3
import os

# Path to the database
UMD_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "mobility.db"
)

class MinHeap:

    def __init__(self, k):
        self.zones = []
        self.k = k

    def size(self):
        return len(self.zones)

    def parent(self, index):
        return (index - 1) // 2

    def left_child(self, index):
        return 2 * index + 1

    def right_child(self, index):
        return 2 * index + 2

    def swap(self, i, j):
        self.zones[i], self.zones[j] = self.zones[j], self.zones[i]

    def bubble_up(self, index):
        while index > 0:
            parent = self._parent(index)
            if self.zones[index][0] < self.zones[parent][0]:
                self.swap(index, parent)
                index = parent
            else:
                break

    def bubble_down(self, index):
        while True:
            smallest = index
            left  = self.left_child(index)
            right = self.right_child(index)

            if left < self.size() and self.zones[left][0] < self.zones[smallest][0]:
                smallest = left

            if right < self.size() and self.zones[right][0] < self.zones[smallest][0]:
                smallest = right

            if smallest != index:
                self.swap(index, smallest)
                index = smallest
            else:
                break

    def add(self, count, location_id, zone_name, borough):

        if self.size() < self.k:
            self.zones.append((count, location_id, zone_name, borough))
            self.bubble_up(self.size() - 1)
        elif count > self.zones[0][0]:
            self.zones[0] = (count, location_id, zone_name, borough)
            self.bubble_down(0)

    def peek_min(self):
        if self.size() == 0:
            return None
        return self.zones[0]

    def get_sorted(self):
        result = list(self.zones)

        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                if result[i][0] < result[j][0]:
                    result[i], result[j] = result[j], result[i]

        return result


def get_top_zones(k=15):
    
    conn = sqlite3.connect(UMD_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pu_location_id,
            pu_zone,
            pu_borough,
            COUNT(*) as trip_count
        FROM taxi_trips
        GROUP BY pu_location_id, pu_zone, pu_borough
    """)

    rows = cursor.fetchall()
    conn.close()

    heap = MinHeap(k)

    for row in rows:
        location_id = row[0]
        zone_name   = row[1]
        borough     = row[2]
        trip_count  = row[3]

        heap.add(trip_count, location_id, zone_name, borough)

    sorted_results = heap.get_sorted()

    results = []
    for item in sorted_results:
        results.append({
            "trip_count":  item[0],
            "location_id": item[1],
            "zone":        item[2],
            "borough":     item[3]
        })

    return results

if __name__ == "__main__":
    print("Top 15 Busiest NYC Taxi Pickup Zones")
    print("=" * 55)
    top_zones = get_top_zones(k=15)
    for rank, zone in enumerate(top_zones, start=1):
        print(f"{rank:>2}. {zone['zone']:<35} {zone['borough']:<15} {zone['trip_count']:>10,} trips")