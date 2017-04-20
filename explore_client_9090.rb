require 'socket'
require 'json'
require_relative 'server/lib/vec'

server = TCPServer.new 9090

class Map
  def initialize(max_width=32, max_height=32)
    @max_width = max_width
    @max_height = max_height
    @map = Array.new(2*@max_width) { Array.new(2*@max_height) { nil } }
  end

  def update_tile(tile)
    # puts tile.inspect
    # puts tile['x']+@max_width
    # puts tile['y']+@max_height
    @map[tile['x']+@max_width][tile['y']+@max_height] = tile
  end

  def tile_walkable?(pos)
    # puts pos
    # puts @map[pos.x][pos.y] && !@map[pos.x][pos.y]['blocked']
    @map[pos.x+@max_width][pos.y+@max_width] && !@map[pos.x+@max_width][pos.y+@max_width]['blocked']
  end

  def tile_unexplored?(pos)
    @map[pos.x+@max_width][pos.y+@max_width].nil?
  end

  def find_nearest_explorable_tile(pos, radius = nil)
    closest_tile(pos, radius) do |map, tile_pos|
      tile_pos != pos && map.tile_walkable?(tile_pos) && closest_tile(tile_pos, 1, &lambda { |map, pos2| map.tile_unexplored?(pos2) })
    end
  end

  def closest_tile(pos, radius = nil, &block)
    # pos = vec(x,y)
    dist = 1
    dir = vec(0, 1)

    loop do
      dist.times do
        return pos if block.call(self, pos)
        pos = pos + dir
      end
      dir = dir.rotate()
      if dir.x == 0
        dist += 1
      end
      break if radius && (dist/2) >= radius && dir.x == 1
    end
    
    return nil
  end



  def pretty
    33.times { puts }
    puts("="*66)
    puts("START")
    @map.transpose.each.with_index do |rows, i|
      STDOUT.write "|"
      rows.each.with_index do |v, j|
        if v.nil?
          STDOUT.write "?"
        elsif v['resources']
          STDOUT.write "$"
        elsif v['blocked']
          STDOUT.write "X"
        else
          STDOUT.write " "
        end
      end
      STDOUT.puts "|"
    end
    puts("="*66)
  end
end

# require 'server/lib/vec'
DIR_VECS = {
  'N' => vec(0,-1),
  'S' => vec(0,1),
  'W' => vec(-1,0),
  'E' => vec(1,0),
}

def move_command(outstanding_unit_cmds, id)
  outstanding_unit_cmds[id] = :move
  dir = ["N","S","E","W"].sample
  cmd = {
    command: "MOVE",
    unit: id,
    dir: dir
  }
  cmd
end



def do_scout_ai(map, outstanding_unit_cmds, id, unit)
  outstanding_unit_cmds[id] = :move
  pos = vec(unit["x"], unit["y"])
  puts pos
  nearest = map.find_nearest_explorable_tile(pos, 10)
  dir = nil
  if nearest
    puts "FOUND TILE!", nearest
    dir_vec = (nearest - pos).closest_cardinal()
    dir = DIR_VECS.invert[dir_vec]
  else
    dir = ["N","S","E","W"].sample
  end
  cmd = {
    command: "MOVE",
    unit: id,
    dir: dir
  }
  cmd
  # dir = ["N","S","E","W"].sample
  
end


loop do
  server_connection = server.accept    # Wait for a server_connection to connect
  units = {}
  outstanding_unit_cmds = {}
  map = Map.new

	while msg = server_connection.gets
    json = JSON.parse(msg)

    @player_id ||= json['player']

    cmds = []
    cmd_msg = {commands: cmds, player_id: @player_id}

    tile_updates = json['tile_updates']
    if tile_updates
      tile_updates.each do |tu|
        map.update_tile tu
      end

      map.pretty
    end

    unit_updates = {}
    (json['unit_updates'] || []).each do |uu|
      unit_updates[uu['id']] = uu
    end

    unit_ids = unit_updates.keys | units.keys
    unit_ids.each do |id|
      if uu = unit_updates[id]
        units[id] =  uu
        if uu['status'] == 'moving'
          outstanding_unit_cmds.delete(id) if outstanding_unit_cmds[id] == :move
        elsif uu['status'] == 'idle'
          cmds << do_scout_ai(map, outstanding_unit_cmds, id, units[id])
        end
      end
      if outstanding_unit_cmds[id] == :move
        cmds << do_scout_ai(map, outstanding_unit_cmds, id, units[id])
      end
    end
    cmds.compact!

    server_connection.puts(cmd_msg.to_json) unless cmds.empty?

  end

  server_connection.close
end