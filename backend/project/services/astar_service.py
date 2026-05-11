import heapq


def heuristic(node, goal, coordinates):
    if not coordinates or node not in coordinates or goal not in coordinates:
        return 0

    x1, y1 = coordinates[node]
    x2, y2 = coordinates[goal]
    return abs(x1 - x2) + abs(y1 - y2)


def reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def astar(graph, start, goal, coordinates=None):
    if not graph:
        return {"error": "empty_graph"}

    if start not in graph:
        return {"error": "invalid_start"}

    if start == goal:
        return {
            "path": [start],
            "total_cost": 0,
            "total_distance": 0,
            "total_time": 0,
        }

    open_heap = []
    heapq.heappush(open_heap, (0, start))
    came_from = {}
    g_costs = {start: 0}
    visited = set()

    while open_heap:
        current_f, current = heapq.heappop(open_heap)

        if current in visited:
            continue

        if current == goal:
            path = reconstruct_path(came_from, current)
            return _calculate_metrics(graph, path)

        visited.add(current)

        for neighbor, edge in graph.get(current, {}).items():
            if not isinstance(edge, dict):
                continue

            edge_distance = edge.get("distance")
            if edge_distance is None:
                edge_distance = edge.get("cost")
            if edge_distance is None:
                continue

            tentative_g = g_costs[current] + edge_distance
            if tentative_g < g_costs.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_costs[neighbor] = tentative_g
                f_cost = tentative_g + heuristic(neighbor, goal, coordinates)
                heapq.heappush(open_heap, (f_cost, neighbor))

    return {"error": "no_path"}


def _calculate_metrics(graph, path):
    total_cost = 0
    total_distance = 0
    total_time = 0

    for index in range(len(path) - 1):
        origin = path[index]
        destination = path[index + 1]
        edge = graph.get(origin, {}).get(destination)
        if not edge:
            return {"error": "missing_edge"}

        total_cost += edge.get("cost", 0)
        total_distance += edge.get("distance", 0)
        total_time += edge.get("time", 0)

    return {
        "path": path,
        "total_cost": total_cost,
        "total_distance": total_distance,
        "total_time": total_time,
    }
