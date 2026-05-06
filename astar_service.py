import heapq

def astar(graph, start, goal):
    pq = [(0, start)]
    visited = set()

    while pq:
        cost, node = heapq.heappop(pq)

        if node == goal:
            return cost

        if node in visited:
            continue

        visited.add(node)

        for neighbor, weight in graph.get(node, {}).items():
            heapq.heappush(pq, (cost + weight, neighbor))

    return float("inf")