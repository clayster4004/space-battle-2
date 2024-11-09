#!/usr/bin/python

import sys
import json
import random

if (sys.version_info > (3, 0)):
    print("Python 3.X detected")
    import socketserver as ss
else:
    print("Python 2.X detected")
    import SocketServer as ss


class NetworkHandler(ss.StreamRequestHandler):
    def handle(self):
        game = Game()

        while True:
            data = self.rfile.readline().decode()  # reads until '\n' encountered
            json_data = json.loads(str(data))
            response = game.process_updates(json_data).encode()
            self.wfile.write(response)


class Unit:
    def __init__(self, unit_data):
        self.id = unit_data['id']
        self.player_id = unit_data['player_id']
        self.x = unit_data['x']
        self.y = unit_data['y']
        self.type = unit_data['type']
        self.status = unit_data['status']
        self.health = unit_data['health']
        self.resource = unit_data.get('resource', 0)

    def update(self, unit_data):
        self.x = unit_data['x']
        self.y = unit_data['y']
        self.status = unit_data['status']
        self.health = unit_data['health']
        self.resource = unit_data.get('resource', self.resource)

    def is_idle(self):
        return self.status == 'idle'


class Tile:
    def __init__(self, tile_data):
        self.x = tile_data['x']
        self.y = tile_data['y']
        self.visible = tile_data['visible']
        self.blocked = tile_data['blocked']
        self.resources = tile_data.get('resources', None)
        self.units = tile_data.get('units', [])

    def update(self, tile_data):
        self.visible = tile_data['visible']
        self.blocked = tile_data['blocked']
        self.resources = tile_data.get('resources', self.resources)
        self.units = tile_data.get('units', self.units)


class World:
    def __init__(self):
        self.units_by_id = {}
        self.tiles = {}

    def update_units(self, unit_updates):
        for unit_data in unit_updates:
            unit_id = unit_data['id']
            if unit_id in self.units_by_id:
                self.units_by_id[unit_id].update(unit_data)
            else:
                self.units_by_id[unit_id] = Unit(unit_data)

    def update_tiles(self, tile_updates):
        for tile_data in tile_updates:
            tile_key = (tile_data['x'], tile_data['y'])
            self.tiles[tile_key] = Tile(tile_data)

    def get_tile(self, x, y):
        return self.tiles.get((x, y))

    def get_adjacent_resource_tile(self, unit):
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # N, S, W, E
        for dx, dy in directions:
            tile = self.get_tile(unit.x + dx, unit.y + dy)
            if tile and tile.resources:
                return tile
        return None


class CommandBuilder:
    MOVE_COMMAND = 'MOVE'
    GATHER_COMMAND = 'GATHER'

    @staticmethod
    def move(unit, direction):
        return {"command": CommandBuilder.MOVE_COMMAND, "unit": unit.id, "dir": direction}

    @staticmethod
    def gather(unit, direction):
        return {"command": CommandBuilder.GATHER_COMMAND, "unit": unit.id, "dir": direction}


class Game:
    def __init__(self):
        self.world = World()
        self.base_location = None
        self.resources = 0
        self.map_width = 0
        self.map_height = 0

    def find_nearest_resource(self, unit):
        """Find the nearest visible resource tile to the given unit."""
        nearest_resource = None
        min_distance = float('inf')
        
        # Search through all visible tiles
        for x in range(self.map_width):
            for y in range(self.map_height):
                tile = self.world.get_tile(x, y)
                if (tile and tile.visible and tile.resources and 
                    not self.is_tile_blocked(x, y)):
                    distance = self.manhattan_distance(unit.x, unit.y, x, y)
                    if distance < min_distance:
                        min_distance = distance
                        nearest_resource = tile
        
        return nearest_resource

    def is_tile_blocked(self, x, y):
        """Check if a tile is blocked."""
        tile = self.world.get_tile(x, y)
        return tile and tile.blocked

    def manhattan_distance(self, x1, y1, x2, y2):
        """Calculate Manhattan distance between two points."""
        return abs(x2 - x1) + abs(y2 - y1)

    def is_adjacent(self, unit, tile):
        """Check if a unit is adjacent to a tile."""
        return self.manhattan_distance(unit.x, unit.y, tile.x, tile.y) == 1

    def is_in_range(self, unit, target):
        """Check if target is within unit's vision/attack range."""
        distance = self.manhattan_distance(unit.x, unit.y, target.x, target.y)
        vision_ranges = {
            'worker': 2,
            'scout': 5,
            'tank': 2
        }
        return distance <= vision_ranges.get(unit.type, 2)

    def get_direction_to_tile(self, unit, tile):
        """Get the direction to move towards a tile."""
        dx = tile.x - unit.x
        dy = tile.y - unit.y
        
        # Prioritize the larger difference to move diagonally
        if abs(dx) > abs(dy):
            return 'E' if dx > 0 else 'W'
        else:
            return 'S' if dy > 0 else 'N'

    def get_direction_to_coordinates(self, unit, target_x, target_y):
        """Get the direction to move towards specific coordinates."""
        dx = target_x - unit.x
        dy = target_y - unit.y
        
        # Prioritize the larger difference to move diagonally
        if abs(dx) > abs(dy):
            return 'E' if dx > 0 else 'W'
        else:
            return 'S' if dy > 0 else 'N'

    def can_afford(self, unit_type):
        """Check if we can afford to create a unit."""
        unit_costs = {
            'worker': 100,
            'scout': 130,
            'tank': 150
        }
        return self.resources >= unit_costs.get(unit_type, float('inf'))

    def find_nearest_enemy(self, unit):
        """Find the nearest visible enemy unit."""
        nearest_enemy = None
        min_distance = float('inf')
        
        for x in range(self.map_width):
            for y in range(self.map_height):
                tile = self.world.get_tile(x, y)
                if tile and tile.visible and tile.units:
                    for enemy in tile.units:
                        distance = self.manhattan_distance(unit.x, unit.y, x, y)
                        if distance < min_distance:
                            min_distance = distance
                            nearest_enemy = enemy
        
        return nearest_enemy

    def find_nearest_worker(self, unit):
        """Find the nearest friendly worker unit."""
        nearest_worker = None
        min_distance = float('inf')
        
        for other_unit in self.world.units_by_id.values():
            if other_unit.type == 'worker' and other_unit.id != unit.id:
                distance = self.manhattan_distance(unit.x, unit.y, 
                                                other_unit.x, other_unit.y)
                if distance < min_distance:
                    min_distance = distance
                    nearest_worker = other_unit
        
        return nearest_worker

    def process_updates(self, json_data):
        # Handle game info on first turn
        if 'game_info' in json_data:
            self.map_width = json_data['game_info']['map_width']
            self.map_height = json_data['game_info']['map_height']
            self.unit_costs = {unit_type: info['cost'] 
                             for unit_type, info in json_data['game_info']['unit_info'].items()
                             if 'cost' in info}

        # Update world state
        if 'unit_updates' in json_data:
            self.world.update_units(json_data['unit_updates'])
            # Track base location
            for unit in json_data['unit_updates']:
                if unit['type'] == 'base':
                    self.base_location = (unit['x'], unit['y'])
                    
        if 'tile_updates' in json_data:
            self.world.update_tiles(json_data['tile_updates'])

        commands = self.get_commands()
        return json.dumps({"commands": commands}, separators=(',', ':')) + '\n'

    def get_commands(self):
        commands = []
        idle_workers = []
        idle_scouts = []
        idle_tanks = []

        # Categorize idle units
        for unit in self.world.units_by_id.values():
            if unit.is_idle():
                if unit.type == 'worker':
                    idle_workers.append(unit)
                elif unit.type == 'scout':
                    idle_scouts.append(unit)
                elif unit.type == 'tank':
                    idle_tanks.append(unit)

        # Worker logic
        for worker in idle_workers:
            if worker.resource > 0:
                # Return to base if carrying resources
                direction = self.get_direction_to_coordinates(worker, self.base_location[0], self.base_location[1])
                commands.append(CommandBuilder.move(worker, direction))
            else:
                # Find nearest visible resource
                resource_tile = self.find_nearest_resource(worker)
                if resource_tile and self.is_adjacent(worker, resource_tile):
                    direction = self.get_direction_to_tile(worker, resource_tile)
                    commands.append(CommandBuilder.gather(worker, direction))
                elif resource_tile:
                    direction = self.get_direction_to_tile(worker, resource_tile)
                    commands.append(CommandBuilder.move(worker, direction))
                else:
                    # Explore if no resources visible
                    direction = self.get_strategic_exploration_direction(worker)
                    commands.append(CommandBuilder.move(worker, direction))

        # Scout logic - prioritize exploration
        for scout in idle_scouts:
            direction = self.get_strategic_exploration_direction(scout)
            commands.append(CommandBuilder.move(scout, direction))

        # Tank logic - protect workers and engage enemies
        for tank in idle_tanks:
            enemy = self.find_nearest_enemy(tank)
            if enemy and self.is_in_range(tank, enemy):
                if self.is_adjacent(tank, enemy):
                    commands.append(CommandBuilder.melee(tank, enemy.id))
                else:
                    dx = enemy.x - tank.x
                    dy = enemy.y - tank.y
                    commands.append(CommandBuilder.shoot(tank, dx, dy))
            else:
                # Patrol near workers if no enemies
                worker = self.find_nearest_worker(tank)
                if worker:
                    direction = self.get_direction_to_coordinates(tank, worker.x, worker.y)
                    commands.append(CommandBuilder.move(tank, direction))

        # Unit creation logic
        if self.base_location and self.can_afford('worker') and self.worker_count < 5:
            commands.append(CommandBuilder.create('worker'))
        elif self.base_location and self.can_afford('scout') and self.scout_count < 2:
            commands.append(CommandBuilder.create('scout'))
        elif self.base_location and self.can_afford('tank') and self.tank_count < 3:
            commands.append(CommandBuilder.create('tank'))

        return commands

    def get_strategic_exploration_direction(self, unit):
        # Weight directions based on:
        # 1. Unexplored tiles
        # 2. Distance from base
        # 3. Known resource locations
        # 4. Other units' positions
        weights = {'N': 0, 'S': 0, 'E': 0, 'W': 0}
        
        # Add weights for unexplored areas
        for direction, (dx, dy) in {'N': (0, -1), 'S': (0, 1), 'E': (1, 0), 'W': (-1, 0)}.items():
            for distance in range(1, 4):
                x, y = unit.x + dx * distance, unit.y + dy * distance
                if 0 <= x < self.map_width and 0 <= y < self.map_height:
                    tile = self.world.get_tile(x, y)
                    if not tile or not tile.visible:
                        weights[direction] += 3 - distance  # Closer unexplored tiles worth more

        # Avoid base direction for scouts
        if unit.type == 'scout' and self.base_location:
            base_direction = self.get_direction_to_coordinates(unit, self.base_location[0], self.base_location[1])
            weights[base_direction] -= 2

        # Choose direction with highest weight
        max_weight = max(weights.values())
        best_directions = [d for d, w in weights.items() if w == max_weight]
        return random.choice(best_directions)


if __name__ == "__main__":
    port = int(sys.argv[1]) if (len(sys.argv) > 1 and sys.argv[1]) else 9090
    host = '0.0.0.0'

    server = ss.TCPServer((host, port), NetworkHandler)
    print("listening on {}:{}".format(host, port))
    server.serve_forever()
