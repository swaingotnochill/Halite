from collections import OrderedDict 
import copy
import numpy as np
import utils
import rule_utils


MOVE_DIRECTIONS = [None, "NORTH", "SOUTH", "EAST", "WEST"]

DISTANCE_MASKS = {}
HALF_PLANES_CATCH = {}
HALF_PLANES_RUN = {}
ROW_COL_DISTANCE_MASKS = {}
DISTANCE_MASK_DIM = 21
half_distance_mask_dim = int(DISTANCE_MASK_DIM/2)
for row in range(DISTANCE_MASK_DIM):
  for col in range(DISTANCE_MASK_DIM):
    # Modified from https://scipy-lectures.org/intro/scipy/auto_examples/solutions/plot_image_blur.html
    horiz_distance = np.minimum(
      np.abs(np.arange(DISTANCE_MASK_DIM) - col),
      np.abs(np.arange(DISTANCE_MASK_DIM) - col - DISTANCE_MASK_DIM))
    horiz_distance = np.minimum(
      horiz_distance,
      np.abs(np.arange(DISTANCE_MASK_DIM) - col + DISTANCE_MASK_DIM))
    
    vert_distance = np.minimum(
      np.abs(np.arange(DISTANCE_MASK_DIM) - row),
      np.abs(np.arange(DISTANCE_MASK_DIM) - row - DISTANCE_MASK_DIM))
    vert_distance = np.minimum(
      vert_distance,
      np.abs(np.arange(DISTANCE_MASK_DIM) - row + DISTANCE_MASK_DIM))
    
    horiz_distance = np.tile(horiz_distance, [DISTANCE_MASK_DIM, 1])
    vert_distance = np.tile(np.expand_dims(vert_distance, 1),
                            [1, DISTANCE_MASK_DIM])
    manh_distance = horiz_distance + vert_distance
    kernel = np.exp(-manh_distance/(DISTANCE_MASK_DIM/4))
    
    DISTANCE_MASKS[(row, col)] = kernel
    
    catch_distance_masks = {}
    run_distance_masks = {}
    
    for d in MOVE_DIRECTIONS[1:]:
      if d == utils.NORTH:
        catch_rows = np.mod(row - np.arange(half_distance_mask_dim) - 1,
                            DISTANCE_MASK_DIM)
        catch_cols = np.arange(DISTANCE_MASK_DIM)
      if d == utils.SOUTH:
        catch_rows = np.mod(row + np.arange(half_distance_mask_dim) + 1,
                            DISTANCE_MASK_DIM)
        catch_cols = np.arange(DISTANCE_MASK_DIM)
      if d == utils.WEST:
        catch_cols = np.mod(col - np.arange(half_distance_mask_dim) - 1,
                            DISTANCE_MASK_DIM)
        catch_rows = np.arange(DISTANCE_MASK_DIM)
      if d == utils.EAST:
        catch_cols = np.mod(col + np.arange(half_distance_mask_dim) + 1,
                            DISTANCE_MASK_DIM)
        catch_rows = np.arange(DISTANCE_MASK_DIM)
        
      catch_mask = np.zeros((DISTANCE_MASK_DIM, DISTANCE_MASK_DIM),
                            dtype=np.bool)
      
      catch_mask[catch_rows[:, None], catch_cols] = 1
      run_mask = np.copy(catch_mask)
      run_mask[row, col] = 1
      
      catch_distance_masks[d] = catch_mask
      run_distance_masks[d] = run_mask
    
    HALF_PLANES_CATCH[(row, col)] = catch_distance_masks
    HALF_PLANES_RUN[(row, col)] = run_distance_masks
    
    for d in range(1, DISTANCE_MASK_DIM):
      ROW_COL_DISTANCE_MASKS[(row, col, d)] = manh_distance == d
    
def update_scores_enemy_ships(
    config, collect_grid_scores, return_to_base_scores, establish_base_scores,
    opponent_ships, halite_ships, row, col, grid_size, spawn_cost, min_dist=2):
  direction_halite_diff_distance={
    utils.NORTH: None,
    utils.SOUTH: None,
    utils.EAST: None,
    utils.WEST: None,
    }
  for row_shift in range(-min_dist, min_dist+1):
    considered_row = (row + row_shift) % grid_size
    for col_shift in range(-min_dist, min_dist+1):
      considered_col = (col + col_shift) % grid_size
      distance = np.abs(row_shift) + np.abs(col_shift)
      if distance <= min_dist:
        if opponent_ships[considered_row, considered_col]:
          relevant_dirs = []
          relevant_dirs += [] if row_shift >= 0 else [utils.NORTH]
          relevant_dirs += [] if row_shift <= 0 else [utils.SOUTH]
          relevant_dirs += [] if col_shift <= 0 else [utils.EAST]
          relevant_dirs += [] if col_shift >= 0 else [utils.WEST]
          
          halite_diff = halite_ships[row, col] - halite_ships[
            considered_row, considered_col]
          for d in relevant_dirs:
            halite_diff_dist = direction_halite_diff_distance[d]
            if halite_diff_dist is None:
              direction_halite_diff_distance[d] = (halite_diff, distance)
            else:
              max_halite_diff = max(halite_diff_dist[0], halite_diff)
              min_ship_dist = min(halite_diff_dist[1], distance)
              direction_halite_diff_distance[d] = (
                max_halite_diff, min_ship_dist)
                
  ship_halite = halite_ships[row, col]
  preferred_directions = []
  valid_directions = copy.copy(MOVE_DIRECTIONS)
  bad_directions = []
  ignore_catch = np.random.uniform() < config['ignore_catch_prob']
  for direction, halite_diff_dist in direction_halite_diff_distance.items():
    if halite_diff_dist is not None:
      halite_diff = halite_diff_dist[0]
      if halite_diff >= 0:
        # I should avoid a collision
        distance_multiplier = 1/halite_diff_dist[1]
        mask_collect_return = HALF_PLANES_RUN[(row, col)][direction]
        valid_directions.remove(direction)
        if halite_diff_dist[1] == 1:
          if None in valid_directions:
            valid_directions.remove(None)
            bad_directions.append(None)
          mask_collect_return[row, col] = True

        # I can still mine halite at the current square if the opponent ship is
        # >1 moves away
        if halite_diff_dist[1] > 1:
          mask_collect_return[row, col] = False
          
        collect_grid_scores -= mask_collect_return*(ship_halite+spawn_cost)*(
          config['collect_run_enemy_multiplier'])*distance_multiplier
        return_to_base_scores -= mask_collect_return*(ship_halite+spawn_cost)*(
          config['return_base_run_enemy_multiplier'])*distance_multiplier
        mask_establish = np.copy(mask_collect_return)
        mask_establish[row, col] = False
        establish_base_scores -= mask_establish*(ship_halite+spawn_cost)*(
          config['establish_base_run_enemy_multiplier'])*distance_multiplier
        
        bad_directions.append(direction)
      elif halite_diff < 0 and not ignore_catch:
        # I would like a collision unless if there is another opponent ship
        # chasing me - risk avoiding policy for now: if there is at least
        # one ship in a direction that has less halite, I should avoid it
        distance_multiplier = 1/halite_diff_dist[1]
        mask_collect_return = HALF_PLANES_CATCH[(row, col)][direction]
        collect_grid_scores -= mask_collect_return*(halite_diff+spawn_cost)*(
          config['collect_catch_enemy_multiplier'])*distance_multiplier
        return_to_base_scores -= mask_collect_return*(halite_diff+spawn_cost)*(
          config['return_base_catch_enemy_multiplier'])*distance_multiplier
        mask_establish = np.copy(mask_collect_return)
        mask_establish[row, col] = False
        establish_base_scores -= mask_establish*(halite_diff+spawn_cost)*(
          config['establish_base_catch_enemy_multiplier'])*distance_multiplier
        
        preferred_directions.append(direction)
        
  return (collect_grid_scores, return_to_base_scores, establish_base_scores,
          preferred_directions, valid_directions, len(bad_directions) == 5)

# Update the scores as a function of blocking enemy bases
def update_scores_blocking_enemy_bases(
    collect_grid_scores, return_to_base_scores, establish_base_scores, row, col,
    grid_size, enemy_bases, valid_directions):
  for d in MOVE_DIRECTIONS[1:]:
    if d == utils.NORTH:
      rows = np.mod(row - (1 + np.arange(half_distance_mask_dim)), grid_size)
      cols = np.repeat(col, half_distance_mask_dim)
      considered_vals = enemy_bases[rows, col]
    elif d == utils.SOUTH:
      rows = np.mod(row + (1 + np.arange(half_distance_mask_dim)), grid_size)
      cols = np.repeat(col, half_distance_mask_dim)
      considered_vals = enemy_bases[rows, col]
    elif d == utils.WEST:
      rows = np.repeat(row, half_distance_mask_dim)
      cols = np.mod(col - (1 + np.arange(half_distance_mask_dim)), grid_size)
      considered_vals = enemy_bases[row, cols]
    elif d == utils.EAST:
      rows = np.repeat(row, half_distance_mask_dim)
      cols = np.mod(col + (1 + np.arange(half_distance_mask_dim)), grid_size)
      considered_vals = enemy_bases[row, cols]
    
    if np.any(considered_vals):
      first_blocking_base_id = np.where(considered_vals)[0][0]
      mask_rows = rows[first_blocking_base_id:]
      mask_cols = cols[first_blocking_base_id:]
      
      collect_grid_scores[mask_rows, mask_cols] = -1e9
      return_to_base_scores[mask_rows, mask_cols] = -1e9
      establish_base_scores[mask_rows, mask_cols] = -1e9
      
      if first_blocking_base_id == 0 and d in valid_directions:
        valid_directions.remove(d)
    
      
  return (collect_grid_scores, return_to_base_scores, establish_base_scores,
          valid_directions)

def set_scores_single_nearby_zero(scores, nearby, size):
  nearby_pos = np.where(nearby)
  row = nearby_pos[0][0]
  col = nearby_pos[1][0]
  
  for i in range(-1, 2):
    near_row = (row + i) % size
    for j in range(-1, 2):
      if i!=0 or j!=0:
        near_col = (col + j) % size
        scores[near_row, near_col] = 0
  
  return scores

def grid_distance(r1, c1, r2, c2, size):
  horiz_diff = c2-c1
  horiz_distance = min(np.abs(horiz_diff),
    min(np.abs(horiz_diff-size), np.abs(horiz_diff+size)))
  vert_diff = r2-r1
  vert_distance = min(np.abs(vert_diff),
    min(np.abs(vert_diff-size), np.abs(vert_diff+size)))
  
  return horiz_distance+vert_distance

def override_early_return_base_scores(
    return_to_base_scores, my_bases, ship_row, ship_col, size, num_ships):
  base_pos = np.where(my_bases)
  base_row = base_pos[0][0]
  base_col = base_pos[1][0]
  
  dist_to_base = grid_distance(base_row, base_col, ship_row, ship_col, size)
  if dist_to_base <= 9-num_ships:
    return_to_base_scores[base_row, base_col] = 0
    
  return return_to_base_scores


def get_ship_scores(config, observation, player_obs, env_config, verbose):
  convert_cost = env_config.convertCost
  spawn_cost = env_config.spawnCost
  my_bases = observation['rewards_bases_ships'][0][1]
  obs_halite = np.maximum(0, observation['halite'])
  # Clip obs_halite to zero when gathering it doesn't add to the score
  # code: delta_halite = int(cell.halite * configuration.collect_rate)
  obs_halite[obs_halite < 1/env_config.collectRate] = 0
  num_ships = len(player_obs[2])
  first_base = num_ships == 1 and my_bases.sum() == 0
  max_ships = config['max_ships']
  early_game_return_boost_step = config['early_game_return_boost_step']
  step = observation['step']
  early_game_not_max_ships = (num_ships < max_ships) and (
    step < early_game_return_boost_step)
  early_game_return_boost = (early_game_return_boost_step-step)/(
    early_game_return_boost_step)*config[
      'early_game_return_base_additional_multiplier']*early_game_not_max_ships
  end_game_return_boost = (step > env_config['episodeSteps']*0.97)*config[
    'end_game_return_base_additional_multiplier']
      
  # Override the maximum number of conversions on the last episode turn
  last_episode_turn = observation['relative_step'] == 1

  grid_size = obs_halite.shape[0]
  # smoothed_friendly_ship_halite = rule_utils.smooth2d(
  #   observation['rewards_bases_ships'][0][3])
  smoothed_halite = rule_utils.smooth2d(obs_halite)
  can_deposit_halite = my_bases.sum() > 0
  opponent_ships = np.stack([
    rbs[2] for rbs in observation['rewards_bases_ships'][1:]]).sum(0)
  halite_ships = np.stack([
    rbs[3] for rbs in observation['rewards_bases_ships']]).sum(0)
  enemy_bases = np.stack([rbs[1] for rbs in observation[
    'rewards_bases_ships']])[1:].sum(0)
  
  ship_scores = {}
  for i, ship_k in enumerate(player_obs[2]):
    row, col = utils.row_col_from_square_grid_pos(
      player_obs[2][ship_k][0], grid_size)
    dm = DISTANCE_MASKS[(row, col)]
    ship_halite = player_obs[2][ship_k][1]
    
    # Scores 1: collecting halite at row, col
    # Multiply the smoothed halite, added with the obs_halite with a distance
    # mask, specific for the current row and column
    collect_grid_scores = dm*(
      smoothed_halite * config['collect_smoothed_multiplier'] + 
      obs_halite * config['collect_actual_multiplier'])
    
    # Override the collect score to 0 to avoid blocking the base early on in
    # the game: All squares right next to the initial base are set to 0
    if observation['rewards_bases_ships'][0][0] >= spawn_cost and (
        observation['step'] < 20) and my_bases.sum() == 1:
      collect_grid_scores = set_scores_single_nearby_zero(
        collect_grid_scores, my_bases, grid_size)
    
    # Scores 2: returning to any of my bases
    return_to_base_scores = my_bases*dm*ship_halite*(
      config['return_base_multiplier'] + early_game_return_boost + (
        end_game_return_boost))
    
    # Override the return base score to 0 to avoid blocking the base early on
    # in the game.
    if observation['rewards_bases_ships'][0][0] >= spawn_cost and (
        observation['step'] < 20) and my_bases.sum() == 1 and num_ships < 9:
      return_to_base_scores = override_early_return_base_scores(
        return_to_base_scores, my_bases, row, col, grid_size, num_ships)
    
    # Scores 3: establish a new base
    establish_base_scores = dm*(
      smoothed_halite-obs_halite) * (config[
        'establish_base_smoothed_multiplier'] + first_base*config[
          'establish_first_base_smoothed_multiplier_correction'])*(
            1-((my_bases*dm).max()))*(1-my_bases) - (
              convert_cost*can_deposit_halite) + ship_halite*(
            config['establish_base_deposit_multiplier'])
            
    # Update the scores as a function of nearby enemy ships to avoid collisions
    # with opposing ships that carry less halite and promote collisions with
    # enemy ships that carry less halite
    (collect_grid_scores, return_to_base_scores, establish_base_scores,
     preferred_directions, valid_directions, 
     agent_surrounded) = update_scores_enemy_ships(
       config, collect_grid_scores, return_to_base_scores,
       establish_base_scores, opponent_ships, halite_ships, row, col,
       grid_size, spawn_cost)
       
    # Update the scores as a function of blocking enemy bases
    (collect_grid_scores, return_to_base_scores, establish_base_scores,
     valid_directions) = update_scores_blocking_enemy_bases(
       collect_grid_scores, return_to_base_scores, establish_base_scores,
       row, col, grid_size, enemy_bases, valid_directions)
            
    if last_episode_turn:
      establish_base_scores[row, col] = 1e9*(ship_halite > convert_cost)
        
    ship_scores[ship_k] = (collect_grid_scores, return_to_base_scores,
                           establish_base_scores, preferred_directions,
                           agent_surrounded, valid_directions)
    
  return ship_scores

def get_ship_plans(config, observation, player_obs, env_config, verbose,
                   all_ship_scores, convert_first_ship_on_None_action=True):
  my_bases = observation['rewards_bases_ships'][0][1]
  can_deposit_halite = my_bases.sum() > 0
  grid_size = observation['halite'].shape[0]
  ship_ids = list(player_obs[2])
  num_ships = len(player_obs[2])
  convert_cost = env_config.convertCost
  num_bases = my_bases.sum()
  new_bases = []
  
  # First, process the convert actions
  ship_plans = OrderedDict()
  for i, ship_k in enumerate(player_obs[2]):
    row, col = utils.row_col_from_square_grid_pos(
      player_obs[2][ship_k][0], grid_size)
    
    ship_scores = all_ship_scores[ship_k]
    ship_halite = player_obs[2][ship_k][1]
    convert_surrounded_ship = ship_scores[4] and (
      ship_halite >= (convert_cost/2)) and (
        ship_halite + player_obs[0] >= convert_cost)
    if ship_scores[2].max() >= max(ship_scores[0].max()*can_deposit_halite,
                                   ship_scores[1].max()) or (
                                     convert_surrounded_ship):
      # Obtain the row and column of the new target base
      target_base = np.where(ship_scores[2] == ship_scores[2].max())
      target_row = target_base[0][0]
      target_col = target_base[1][0]
      
      if (target_row == row and target_col == col) or convert_surrounded_ship:
        ship_plans[ship_k] = rule_utils.CONVERT
        new_bases.append((row, col))
        my_bases[row, col] = True
        can_deposit_halite = True
      else:
        ship_plans[ship_k] = (target_row, target_col, ship_scores[3])
        
  # Next, do another pass to coordinate the target squares. This is done in a
  # single pass for now where the selection order is determined based on the 
  # availability of > 1 direction in combination with the initial best score
  ship_priority_scores = np.zeros(num_ships)
  for i, ship_k in enumerate(player_obs[2]):
    ship_scores = all_ship_scores[ship_k]
    for (r, c) in new_bases:
      ship_scores[0][r, c] = 0
      ship_scores[2][r, c] = 0
    all_ship_scores[ship_k] = ship_scores
    
    ship_priority_scores[i] = np.stack([
      ship_scores[0], ship_scores[1], ship_scores[2]]).max() + (
        1e9*(len(ship_scores[5]) == 1))
    
  ship_order = np.argsort(-ship_priority_scores)
  occupied_target_squares = []
  return_base_distances = []
  for i in range(num_ships):
    ship_k = ship_ids[ship_order[i]]
    if not ship_k in ship_plans:
      row, col = utils.row_col_from_square_grid_pos(
        player_obs[2][ship_k][0], grid_size)
      ship_scores = all_ship_scores[ship_k]
      
      for (r, c) in occupied_target_squares:
        ship_scores[0][r, c] = 0
        ship_scores[2][r, c] = 0

      for (r, c, d) in return_base_distances:
        if grid_distance(r, c, row, col, grid_size) == d:
          ship_scores[1][r, c] = 0
      
      best_collect_score = ship_scores[0].max()
      best_return_score = ship_scores[1].max()
      best_establish_score = ship_scores[2].max()
      
      if best_collect_score >= max(best_return_score, best_establish_score):
        # Gather mode
        target_gather = np.where(ship_scores[0] == ship_scores[0].max())
        target_row = target_gather[0][0]
        target_col = target_gather[1][0]
        
        if target_row == row and target_col == col and num_ships == 1 and (
            num_bases == 0) and convert_first_ship_on_None_action:
          ship_plans[ship_k] = rule_utils.CONVERT
          my_bases[row, col] = True
          occupied_target_squares.append((row, col))
        else:
          ship_plans[ship_k] = (target_row, target_col, ship_scores[3])
          occupied_target_squares.append((target_row, target_col))
      elif best_return_score >= best_establish_score:
        # Return base mode
        # TODO: pick a new established base if that is closer
        target_return = np.where(ship_scores[1] == ship_scores[1].max())
        target_row = target_return[0][0]
        target_col = target_return[1][0]
        ship_plans[ship_k] = (target_row, target_col, ship_scores[3])
        base_distance = grid_distance(target_row, target_col, row, col,
                                      grid_size)
        return_base_distances.append((target_row, target_col, base_distance))
      else:
        # Establish base mode
        target_base = np.where(ship_scores[2] == ship_scores[2].max())
        target_row = target_base[0][0]
        target_col = target_base[1][0]
        ship_plans[ship_k] = (target_row, target_col, ship_scores[3])
        occupied_target_squares.append((target_row, target_col))
      
  return ship_plans, my_bases

def get_dir_from_target(row, col, target_row, target_col, grid_size):
  horiz_diff = target_col-col
  horiz_distance = min(np.abs(horiz_diff),
    min(np.abs(horiz_diff-grid_size), np.abs(horiz_diff+grid_size)))
  vert_diff = target_row-row
  vert_distance = min(np.abs(vert_diff),
    min(np.abs(vert_diff-grid_size), np.abs(vert_diff+grid_size)))
  
  half_grid = grid_size / 2
  shortest_directions = []
  if horiz_distance > 0:
    if target_col > col:
      shortest_dirs = [utils.EAST if (target_col - col) <= half_grid else (
        utils.WEST)]
    else:
      shortest_dirs = [utils.WEST if (col - target_col) <= half_grid else (
        utils.EAST)]
    if horiz_distance == grid_size/2:
      shortest_dirs = [utils.EAST, utils.WEST]
    shortest_directions.extend(shortest_dirs)
  if vert_distance > 0:
    if target_row > row:
      shortest_dirs = [utils.SOUTH if (target_row - row) <= half_grid else (
        utils.NORTH)]
    else:
      shortest_dirs = [utils.NORTH if (row - target_row) <= half_grid else (
        utils.SOUTH)]
    if vert_distance == grid_size/2:
      shortest_dirs = [utils.NORTH, utils.SOUTH]
    shortest_directions.extend(shortest_dirs)
    
  return shortest_directions

def map_ship_plans_to_actions(config, observation, player_obs, env_config,
                              verbose, ship_scores, ship_plans):
  ship_actions = {}
  remaining_budget = player_obs[0]
  convert_cost = env_config.convertCost
  obs_halite = np.maximum(0, observation['halite'])
  # Clip obs_halite to zero when gathering it doesn't add to the score
  # code: delta_halite = int(cell.halite * configuration.collect_rate)
  obs_halite[obs_halite < 1/env_config.collectRate] = 0
  grid_size = obs_halite.shape[0]
  num_ships = len(player_obs[2])
  my_next_ships = np.zeros((grid_size, grid_size), dtype=np.bool)
  updated_ship_pos = {}
  
  # List all positions you definitely don't want to move to. Initially this
  # only contains enemy bases and eventually also earlier ships.
  bad_positions = np.stack([rbs[1] for rbs in observation[
    'rewards_bases_ships']])[1:].sum(0)
  
  # Order the ship plans based on the available valid direction count. Break
  # ties using the original order
  move_valid_actions = OrderedDict()
  ship_priority_scores = np.zeros(num_ships)
  ship_key_plans = list(ship_plans)
  for i, ship_k in enumerate(ship_key_plans):
    row, col = utils.row_col_from_square_grid_pos(
      player_obs[2][ship_k][0], grid_size)
    valid_actions = []
    if not isinstance(ship_plans[ship_k], str):
      target_row, target_col, preferred_directions = ship_plans[ship_k]
      shortest_actions = get_dir_from_target(row, col, target_row, target_col,
                                             grid_size)
      
      # Filter out bad positions from the shortest actions
      for a in shortest_actions:
        move_row, move_col = rule_utils.move_ship_row_col(
          row, col, a, grid_size)
        if not bad_positions[move_row, move_col]:
          valid_actions.append(a)
      move_valid_actions[ship_k] = valid_actions
  
    ship_priority_scores[i] = -1e6*len(ship_scores[ship_k][5]) -1e3*len(
      valid_actions) - i
  
  ship_order = np.argsort(-ship_priority_scores)
  ordered_ship_plans = [ship_key_plans[o] for o in ship_order]
  
  for ship_k in ordered_ship_plans:
    row, col = utils.row_col_from_square_grid_pos(
      player_obs[2][ship_k][0], grid_size)
    if isinstance(ship_plans[ship_k], str):
      ship_actions[ship_k] = ship_plans[ship_k]
      obs_halite[row, col] = 0
      remaining_budget -= convert_cost
    else:
      target_row, target_col, preferred_directions = ship_plans[ship_k]
      shortest_actions = get_dir_from_target(row, col, target_row, target_col,
                                             grid_size)
      
      # Filter out bad positions from the shortest actions
      valid_actions = []
      for a in shortest_actions:
        move_row, move_col = rule_utils.move_ship_row_col(
          row, col, a, grid_size)
        if not bad_positions[move_row, move_col]:
          valid_actions.append(a)
      if valid_actions:
        if preferred_directions:
          # TODO: figure out if this is actually helpful (it makes the agent
          # very predictable)
          intersect_directions = list(set(valid_actions) & set(
            preferred_directions))
          if intersect_directions:
            valid_actions = intersect_directions
        action = str(np.random.choice(valid_actions))
      else:
        action = None
        if bad_positions[row, col]:
          # Pick a random, not bad action
          shuffled_actions = np.random.permutation(MOVE_DIRECTIONS[1:])
          for a in shuffled_actions:
            move_row, move_col = rule_utils.move_ship_row_col(
              row, col, a, grid_size)
            if not bad_positions[move_row, move_col]:
              action = str(a)
              break
      
      # Update my_next_ships
      new_row, new_col = rule_utils.move_ship_row_col(
        row, col, action, grid_size)
      my_next_ships[new_row, new_col] = 1
      bad_positions[new_row, new_col] = 1
      updated_ship_pos[ship_k] = (new_row, new_col)
      if action is not None:
        ship_actions[ship_k] = action
  
  return (ship_actions, remaining_budget, my_next_ships, obs_halite,
          updated_ship_pos)

def decide_existing_base_spawns(
    config, observation, player_obs, my_next_bases, my_next_ships, obs_halite,
    env_config, remaining_budget, verbose, ship_plans, updated_ship_pos):

  spawn_cost = env_config.spawnCost
  num_ships = my_next_ships.sum()
  max_spawns = int(remaining_budget/spawn_cost)
  max_spawns = min(max_spawns, int(config['max_ships']-num_ships))
  max_allowed_ships = config['max_ships']
  total_ship_count = np.stack([
    rbs[2] for rbs in observation['rewards_bases_ships']]).sum()
  max_spawns = min(max_spawns, int(max_allowed_ships - num_ships))
  max_spawns = min(max_spawns, int(obs_halite.sum()/2/spawn_cost))
  relative_step = observation['relative_step']
  max_spawns = min(max_spawns, int(
    obs_halite.sum()/min(total_ship_count+1e-9, (num_ships+1e-9)*2)/spawn_cost*(
      1-relative_step)*398/config['max_spawn_relative_step_divisor']))
  last_episode_turn = observation['relative_step'] == 1

  if max_spawns <= 0 or not player_obs[1] or last_episode_turn:
    return {}, remaining_budget
  
  num_bases = len(player_obs[1])
  spawn_scores = np.zeros(num_bases)
  grid_size = obs_halite.shape[0]
  smoothed_friendly_ship_halite = rule_utils.smooth2d(
    observation['rewards_bases_ships'][0][3])
  smoothed_halite = rule_utils.smooth2d(obs_halite)
  
  for i, base_k in enumerate(player_obs[1]):
    row, col = utils.row_col_from_square_grid_pos(
      player_obs[1][base_k], grid_size)
    
    # Don't spawn when there will be a ship at the base
    spawn_scores[i] -= 1e9*my_next_ships[row, col]
    
    # Don't spawn when there is a returning ship that wants to enter the base
    # in two steps
    for k in ship_plans:
      if ship_plans[k][0] == row and ship_plans[k][1] == col:
        updated_distance = grid_distance(row, col, updated_ship_pos[k][0],
                                         updated_ship_pos[k][1], grid_size)
        if updated_distance == 1:
          spawn_scores[i] -= 1e6
          break
    
    # Spawn less when the base is crowded with ships with a lot of halite
    # TODO: use the updated ship halite
    spawn_scores[i] -= smoothed_friendly_ship_halite[row, col]*(
      config['nearby_ship_halite_spawn_constant'])
        
    # Spawn more when there is a lot of nearby halite
    spawn_scores[i] += smoothed_halite[row, col]*(
      config['nearby_halite_spawn_constant'])
    
    # Spawn more when there is a lot of remaining budget available
    spawn_scores[i] += remaining_budget*(
      config['remaining_budget_spawn_constant'])
    
    if verbose:
        print(smoothed_friendly_ship_halite[row, col]*(
          config['nearby_ship_halite_spawn_constant']),
          smoothed_halite[row, col]*(
            config['nearby_halite_spawn_constant']),
          remaining_budget*(config['remaining_budget_spawn_constant']),
          )
    
  if verbose:
    print("Spawn scores and threshold: {}; {}".format(
      spawn_scores, config['spawn_score_threshold']))
    
  # Convert the ships with the top conversion scores that stay within the
  # max conversion limits
  spawn_ids = np.where(spawn_scores > config[
    'spawn_score_threshold'])[0][:max_spawns]
  
  mapped_actions = {}
  for i, base_k in enumerate(player_obs[1]):
    if np.isin(i, spawn_ids):
      mapped_actions[base_k] = rule_utils.SPAWN
      remaining_budget -= spawn_cost
      
  return mapped_actions, remaining_budget

def get_config_actions(config, observation, player_obs, env_config,
                       verbose=False):
  # Compute the ship scores for all high level actions
  ship_scores = get_ship_scores(config, observation, player_obs, env_config,
                                verbose)
  
  # Compute the coordinated high level ship plan
  ship_plans, my_next_bases = get_ship_plans(
    config, observation, player_obs, env_config, verbose, ship_scores)
  
  # Translate the ship high level plans to basic move/convert actions
  (mapped_actions, remaining_budget, my_next_ships, my_next_halite,
   updated_ship_pos) = map_ship_plans_to_actions(
     config, observation, player_obs, env_config, verbose, ship_scores,
     ship_plans)
  
  # Decide for all bases whether to spawn or keep the base available
  base_actions, remaining_budget = decide_existing_base_spawns(
    config, observation, player_obs, my_next_bases, my_next_ships,
    my_next_halite, env_config, remaining_budget, verbose, ship_plans,
    updated_ship_pos)
  
  mapped_actions.update(base_actions)
  halite_spent = player_obs[0]-remaining_budget
  
  step_details = {
    'ship_scores': ship_scores,
    'ship_plans': ship_plans,
    'mapped_actions': mapped_actions,
    'observation': observation,
    'player_obs': player_obs,
    }
  
  return mapped_actions, halite_spent, step_details