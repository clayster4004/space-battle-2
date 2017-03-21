require 'gosu'
require 'awesome_print'
require 'json'
require 'easy_diff'
# require 'pry'

require_relative 'lib/vec'
require_relative 'components/components'
require_relative 'lib/prefab'
require_relative 'systems/render_system'
require_relative 'systems/systems'
require_relative 'lib/world'
require_relative 'lib/map'
require_relative 'lib/entity_manager'
require_relative 'lib/input_cacher'
require_relative 'lib/network_manager'

module Enumerable
  def sum
    size > 0 ? inject(0, &:+) : 0
  end
end

ASSETS = {
  dirt1: 'assets/PNG/Default Size/Tile/scifiTile_41.png',
  dirt2: 'assets/PNG/Default Size/Tile/scifiTile_42.png',
  tree1: 'assets/PNG/Default Size/Environment/scifiEnvironment_14.png',
  base1: 'assets/PNG/Default Size/Structure/scifiStructure_01.png',
}

class RtsGame < Gosu::Window
  MAX_UPDATE_SIZE_IN_MILLIS = 500
  def initialize
    super(1024,1024,false)
    @input_cacher = InputCacher.new
    @last_millis = Gosu::milliseconds.to_f
    build_world
  end

  def needs_cursor?
    true
  end

  TURN_DURATION = 100
  def update
    self.caption = "FPS: #{Gosu.fps} ENTS: #{@entity_manager.num_entities}"

    delta = relative_delta
    input = take_input_snapshot

    if @start
      @turn_count ||= 0
      @turn_time += delta
      if @turn_time > TURN_DURATION
        @turn_count += 1
        @turn_time -= TURN_DURATION
        input[:messages] = @network_manager.pop_messages!
        @network_manager.clients.each do |player_id|
          msg = generate_message_for(@entity_manager, player_id, @turn_count)
          @network_manager.write(player_id, msg)
        end
        @network_manager.flush!
      end
    end

    @world.update @entity_manager, delta, input, @resources
  end

  def generate_message_for(entity_manager, player_id, turn_count)
    # TODO this in a new thread?
    @state_cache ||= {}
    prev_state = @state_cache[player_id] || {}
    new_state = build_state_for_player(entity_manager, player_id)
    @state_cache[player_id] = new_state
    msg = build_diff_message(prev_state, new_state)
    msg.merge!( player: player_id, turn: turn_count)
    msg.to_json
  end

  def build_state_for_player(entity_manager, player_id)
    units = []
    # TODO query based on values  :(
    entity_manager.each_entity(Unit, PlayerOwned) do |ent|
      u, player = ent.components
      if player.id == player_id
        units << { id: ent.id, player_id: player.id }
      end
    end
    {units: units}
  end

  def build_diff_message(prev_state, new_state)
    rem, diff = prev_state.easy_diff(new_state)
    msg = {}
    msg[:unit_updates] = diff[:units] if diff[:units]
    msg[:tile_updates] = diff[:tiles] if diff[:tiles]
    msg
  end

  def draw
    @render_system.draw self, @entity_manager, @resources
  end

  def button_down(id)
    close if id == Gosu::KbEscape
    if @start
      @input_cacher.button_down id
    else
      @start = true
    end
  end

  def button_up(id)
    @input_cacher.button_up id
  end
  private

  def preload_assets!(res)
    images = {}
    images[:dirt1] = Gosu::Image.new(ASSETS[:dirt1], tileable: true)
    images[:dirt2] = Gosu::Image.new(ASSETS[:dirt2], tileable: true)
    images[:tree1] = Gosu::Image.new(ASSETS[:tree1])
    images[:base1] = Gosu::Image.new(ASSETS[:base1])

    # TODO add sounds and music here?

    res[:images] = images
  end

  def load_map!(res)
    res[:map] = Map.generate(32,32)
  end

  def build_world
    @turn_time = 0
    @resources = {}
    load_map! @resources
    preload_assets! @resources
    @entity_manager = EntityManager.new
    @network_manager = NetworkManager.new
    @network_manager.connect("localhost", "9090")

    Prefab.map(entity_manager: @entity_manager, resources: @resources)

    @world = World.new [
      CommandSystem.new,
      TimerSystem.new,
      TimedSystem.new,
      TimedLevelSystem.new,
      SoundSystem.new,
    ]
    @render_system = RenderSystem.new
  end

  def relative_delta
    total_millis = Gosu::milliseconds.to_f
    delta = total_millis
    delta -= @last_millis if total_millis > @last_millis
    @last_millis = total_millis
    delta = MAX_UPDATE_SIZE_IN_MILLIS if delta > MAX_UPDATE_SIZE_IN_MILLIS
    delta
  end

  def take_input_snapshot
    total_millis = Gosu::milliseconds.to_f

    mouse_pos = {x: mouse_x, y: mouse_y}
    input_snapshot = @input_cacher.snapshot @last_snapshot, total_millis, mouse_pos
    @last_snapshot = input_snapshot
    input_snapshot
  end
end

if $0 == __FILE__
  $window = RtsGame.new
  $window.show
end