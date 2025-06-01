import random
from typing import Tuple, Optional, List, Dict

from game.logic.base import BaseLogic
from game.models import GameObject, Board, Position, Feature
from game.util import get_direction, position_equals, clamp

# --- Constants ---
BLUE_DIAMOND_VALUE = 1
RED_DIAMOND_VALUE = 2
DEFAULT_INVENTORY_SIZE = 5
TOTAL_GAME_TIME_MS = 60 * 1000 

# Thresholds and weights
TIME_SAFETY_MARGIN_MOVES = 15 

TACKLE_RADIUS = 1
TACKLE_MIN_OPPONENT_DIAMONDS = 1 
OPPONENT_HIGH_DIAMOND_COUNT = 3 
RED_BUTTON_PROXIMITY_ADVANTAGE = 3 
DIAMONDS_BEFORE_CONSIDERING_RED_OPTIMIZATION = 4
LOW_DIAMOND_COUNT_FOR_RED_BUTTON = 3

URGENT_TIME_PERCENTAGE = 0.25 # Persentase sisa waktu yg dianggap mendesak
NORMAL_RETURN_THRESHOLD_PERCENT = 0.8 
URGENT_RETURN_THRESHOLD_PERCENT = 0.5 # Ini lebih ke "jika waktu mendesak, minimal bawa segini baru pulang"

BASE_MIN_TARGET_EVALUATION = 0.04 
URGENT_MIN_TARGET_EVALUATION = 0.01

DIAMOND_TO_BASE_DISTANCE_PENALTY_FACTOR = 0.25 
COMPETITIVE_DIAMOND_PENALTY_FACTOR = 0.07 


class Garox(BaseLogic):
    def __init__(self):
        self.goal_position: Optional[Position] = None
        self.current_target_is_teleporter_entry: bool = False
        self.fallback_directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        self.current_fallback_direction_index = 0
        # self.opponent_estimated_bases: Dict[str, Position] = {} 

    def _manhattan_distance(self, pos1: Position, pos2: Position) -> int:
        return abs(pos1.x - pos2.x) + abs(pos1.y - pos2.y)

    def _get_teleporters(self, board: Board) -> List[Tuple[GameObject, Optional[GameObject]]]:
        teleporters_on_board = [obj for obj in board.game_objects if obj.type == "TeleportGameObject"]
        paired_teleporters = []
        processed_ids = set()
        for tp1 in teleporters_on_board:
            if tp1.id in processed_ids: continue
            if tp1.properties and tp1.properties.pair_id:
                tp2 = next((tp_other for tp_other in teleporters_on_board if tp_other.id == tp1.properties.pair_id), None)
                paired_teleporters.append((tp1, tp2))
                processed_ids.add(tp1.id)
                if tp2: processed_ids.add(tp2.id)
        return paired_teleporters

    def _calculate_effective_distance_and_path(
        self, start_pos: Position, end_pos: Position, board: Board,
        teleporters: List[Tuple[GameObject, Optional[GameObject]]]
    ) -> Tuple[int, Optional[Position], bool]:
        direct_distance = self._manhattan_distance(start_pos, end_pos)
        best_distance = direct_distance
        path_via_teleporter_target: Optional[Position] = end_pos
        uses_teleporter = False
        for tp_entry_obj, tp_exit_obj in teleporters:
            if not tp_exit_obj: continue
            tp_entry_pos, tp_exit_pos = tp_entry_obj.position, tp_exit_obj.position
            if position_equals(start_pos, tp_entry_pos) or position_equals(start_pos, tp_exit_pos): continue
            dist_to_tp_entry = self._manhattan_distance(start_pos, tp_entry_pos)
            dist_from_tp_exit_to_end = self._manhattan_distance(tp_exit_pos, end_pos)
            teleporter_path_distance = dist_to_tp_entry + 1 + dist_from_tp_exit_to_end 
            if teleporter_path_distance < best_distance:
                best_distance = teleporter_path_distance
                path_via_teleporter_target = tp_entry_pos
                uses_teleporter = True
        return best_distance, path_via_teleporter_target, uses_teleporter

    def _get_safe_random_move_or_cycle(self, current_pos: Position, board: Board) -> Tuple[int, int]:
        options = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        random.shuffle(options)
        for dx, dy in options: 
            if board.is_valid_move(current_pos, dx, dy):
                self.current_fallback_direction_index = 0
                return dx, dy
        for _ in range(len(self.fallback_directions)):
            dx, dy = self.fallback_directions[self.current_fallback_direction_index]
            self.current_fallback_direction_index = (self.current_fallback_direction_index + 1) % len(self.fallback_directions)
            if board.is_valid_move(current_pos, dx, dy): return dx, dy
        return 0, 0 
    
    # FUNGSI _handle_safety_check DIHAPUS KARENA PERMINTAAN BOT FULL OFENSIF

    def next_move(self, board_bot: GameObject, board: Board) -> Tuple[int, int]:
        my_props = board_bot.properties
        current_pos = board_bot.position
        my_base = my_props.base

        inventory_size = my_props.inventory_size if my_props.inventory_size is not None else DEFAULT_INVENTORY_SIZE
        diamonds_held = my_props.diamonds if my_props.diamonds is not None else 0
        time_left_ms = my_props.milliseconds_left if my_props.milliseconds_left is not None else float('inf')
        
        teleporters = self._get_teleporters(board)
        all_other_bots = [b for b in board.bots if b.properties.name != my_props.name]

        if self.goal_position and position_equals(current_pos, self.goal_position):
            self.goal_position = None 
            self.current_target_is_teleporter_entry = False

        final_dx, final_dy = 0, 0 

        # --- 1. Dynamic Return to Base Logic (DIPERKETAT) ---
        dist_to_base, path_target_base, use_tp_base = self._calculate_effective_distance_and_path(
            current_pos, my_base, board, teleporters
        )
        
        


        time_per_move_ms = board.minimum_delay_between_moves if board.minimum_delay_between_moves > 0 else 100
        # Perhitungan waktu pulang yang lebih konservatif
        time_needed_to_return_ms = (dist_to_base * time_per_move_ms) + (TIME_SAFETY_MARGIN_MOVES * time_per_move_ms)
        


        is_inventory_full = diamonds_held >= inventory_size
        is_time_critical_for_return = time_left_ms <= time_needed_to_return_ms # Kondisi utama untuk waktu
        
        # Tentukan ambang batas inventory untuk "urgent return" berdasarkan sisa waktu
        # Ini lebih berarti "jika waktu sudah urgent, minimal bawa segini baru consider pulang karena waktu"
        min_diamonds_for_urgent_time_return = inventory_size * URGENT_RETURN_THRESHOLD_PERCENT
        if time_left_ms < (TOTAL_GAME_TIME_MS * URGENT_TIME_PERCENTAGE) and \
           diamonds_held >= min_diamonds_for_urgent_time_return and \
           is_time_critical_for_return:
            # Jika waktu sudah masuk kategori urgent DAN kita bawa cukup diamond DAN waktu memang kritis, pulang
            must_return_due_to_urgent_time_and_inventory = True
        else:
            must_return_due_to_urgent_time_and_inventory = False

        must_return = False
        if is_inventory_full: 
            must_return = True
        elif diamonds_held > 0 and is_time_critical_for_return: 
            must_return = True


        if must_return:
            if position_equals(current_pos, my_base):
                self.goal_position = None
                final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board) 
            else:
                self.goal_position = path_target_base
                self.current_target_is_teleporter_entry = use_tp_base and \
                    (path_target_base is not None and not position_equals(path_target_base, my_base))
                if self.goal_position and not position_equals(current_pos, self.goal_position):
                    final_dx, final_dy = get_direction(current_pos.x, current_pos.y, self.goal_position.x, self.goal_position.y)
                elif self.goal_position and position_equals(current_pos, self.goal_position) and self.current_target_is_teleporter_entry:
                    final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board)
            return final_dx, final_dy


        # --- 2. Evaluate Single Best Diamond ---
        diamond_candidates_eval = [] 
        available_diamonds = board.diamonds
        
        if available_diamonds:
            for diamond in available_diamonds:
                if position_equals(current_pos, diamond.position): continue
                diamond_value_raw = diamond.properties.points if diamond.properties and diamond.properties.points is not None else BLUE_DIAMOND_VALUE
                if diamonds_held + diamond_value_raw > inventory_size and \
                   not (diamonds_held == DIAMONDS_BEFORE_CONSIDERING_RED_OPTIMIZATION and diamond_value_raw == BLUE_DIAMOND_VALUE):
                    continue
                dist_to_diamond, path_target_to_diamond, uses_tp_to_diamond = self._calculate_effective_distance_and_path(
                    current_pos, diamond.position, board, teleporters
                )
                if dist_to_diamond == 0 : continue
                effective_diamond_value = float(diamond_value_raw)
                num_closer_opponents = 0
                for other_bot in all_other_bots:
                    dist_opp_to_diamond, _, _ = self._calculate_effective_distance_and_path(
                        other_bot.position, diamond.position, board, teleporters
                    )
                    if dist_opp_to_diamond < dist_to_diamond:
                        num_closer_opponents += 1
                if num_closer_opponents > 0:
                    penalty = (num_closer_opponents**2) * COMPETITIVE_DIAMOND_PENALTY_FACTOR
                    effective_diamond_value *= (1.0 - penalty)
                    if effective_diamond_value < 0: effective_diamond_value = 0.01
                
                dist_diamond_to_base, _, _ = self._calculate_effective_distance_and_path(
                    diamond.position, my_base, board, teleporters
                )
                current_total_diamonds_if_taken = diamonds_held + diamond_value_raw
                inventory_fill_ratio = (current_total_diamonds_if_taken / inventory_size) if inventory_size > 0 else 1
                return_penalty_factor = 1.0 + (DIAMOND_TO_BASE_DISTANCE_PENALTY_FACTOR * inventory_fill_ratio)
                total_trip_distance = dist_to_diamond + (dist_diamond_to_base * return_penalty_factor)
                
                evaluation_score = 0
                if total_trip_distance > 0:
                    evaluation_score = effective_diamond_value / total_trip_distance
                
                diamond_candidates_eval.append({
                    'score': evaluation_score, 'diamond': diamond, 
                    'path_target': path_target_to_diamond, 'uses_tp': uses_tp_to_diamond, 
                    'value_raw': diamond_value_raw, 'dist_collect': dist_to_diamond
                })
            diamond_candidates_eval.sort(key=lambda x: x['score'], reverse=True)

        best_diamond_data: Optional[dict] = None
        if len(diamond_candidates_eval) > 0:
            if diamonds_held == DIAMONDS_BEFORE_CONSIDERING_RED_OPTIMIZATION:
                blue_candidate_when_4_diamonds = next(
                    (cand for cand in diamond_candidates_eval if cand['value_raw'] == BLUE_DIAMOND_VALUE and diamonds_held + cand['value_raw'] <= inventory_size), 
                    None
                )
                if blue_candidate_when_4_diamonds:
                    best_diamond_data = blue_candidate_when_4_diamonds
                elif diamond_candidates_eval[0]['value_raw'] == RED_DIAMOND_VALUE and \
                     (diamonds_held + diamond_candidates_eval[0]['value_raw'] > inventory_size):
                    if len(diamond_candidates_eval) > 1 and \
                       (diamonds_held + diamond_candidates_eval[1]['value_raw'] <= inventory_size) : 
                        best_diamond_data = diamond_candidates_eval[1]
                elif diamonds_held + diamond_candidates_eval[0]['value_raw'] <= inventory_size: # Kandidat terbaik muat
                    best_diamond_data = diamond_candidates_eval[0]
            else: 
                best_diamond_data = next(
                    (cand for cand in diamond_candidates_eval if diamonds_held + cand['value_raw'] <= inventory_size),
                    None
                )

        # --- 3. Strategic Red Button Usage ---
        red_button_obj: Optional[GameObject] = next((obj for obj in board.game_objects if obj.type == "DiamondButtonGameObject"), None)
        use_red_button_action = False
        
        if red_button_obj and not position_equals(current_pos, red_button_obj.position):
            dist_to_red_button_val = self._manhattan_distance(current_pos, red_button_obj.position)
            if best_diamond_data and dist_to_red_button_val < best_diamond_data['dist_collect'] - RED_BUTTON_PROXIMITY_ADVANTAGE :
                use_red_button_action = True
            elif len(available_diamonds) <= LOW_DIAMOND_COUNT_FOR_RED_BUTTON and dist_to_red_button_val <= 5 :
                use_red_button_action = True
        
        current_min_target_eval = BASE_MIN_TARGET_EVALUATION
        if time_left_ms < (TOTAL_GAME_TIME_MS * URGENT_TIME_PERCENTAGE):
            current_min_target_eval = URGENT_MIN_TARGET_EVALUATION

        if use_red_button_action and red_button_obj :
            is_red_button_worth_it = False
            if not best_diamond_data: 
                is_red_button_worth_it = True
            elif best_diamond_data and self._manhattan_distance(current_pos, red_button_obj.position) < best_diamond_data['dist_collect'] - RED_BUTTON_PROXIMITY_ADVANTAGE:
                is_red_button_worth_it = True 
            elif len(available_diamonds) <= LOW_DIAMOND_COUNT_FOR_RED_BUTTON:
                is_red_button_worth_it = True
                
            if is_red_button_worth_it:
                self.goal_position = red_button_obj.position
                self.current_target_is_teleporter_entry = False
                final_dx, final_dy = get_direction(current_pos.x, current_pos.y, self.goal_position.x, self.goal_position.y)
                return final_dx, final_dy 

        # --- 4. Go for Chosen Best Single Diamond ---
        if best_diamond_data and best_diamond_data['score'] >= current_min_target_eval:
            if position_equals(current_pos, best_diamond_data['path_target']):
                if best_diamond_data['uses_tp'] and not position_equals(best_diamond_data['path_target'], best_diamond_data['diamond'].position):
                    final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board)
                else:
                    self.goal_position = None
                    final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board)
                return final_dx, final_dy 

            self.goal_position = best_diamond_data['path_target']
            self.current_target_is_teleporter_entry = best_diamond_data['uses_tp'] and \
                (self.goal_position is not None and not position_equals(self.goal_position, best_diamond_data['diamond'].position))
            final_dx, final_dy = get_direction(current_pos.x, current_pos.y, self.goal_position.x, self.goal_position.y)
            return final_dx, final_dy

        # --- 5. Strategic Tackle Opponent ---
        opponents_to_consider = []
        my_time = my_props.milliseconds_left if my_props.milliseconds_left is not None else 0
        if not best_diamond_data or (best_diamond_data and best_diamond_data['score'] < current_min_target_eval):
            for opp_obj in all_other_bots: 
                opp_diamonds = opp_obj.properties.diamonds if opp_obj.properties.diamonds is not None else 0
                if opp_diamonds >= TACKLE_MIN_OPPONENT_DIAMONDS:
                    opp_dist = self._manhattan_distance(current_pos, opp_obj.position)
                    if opp_dist <= TACKLE_RADIUS:
                        if diamonds_held < 2 or opp_diamonds >= OPPONENT_HIGH_DIAMOND_COUNT :
                           tackle_score = opp_diamonds / opp_dist if opp_dist > 0 else float('inf')
                           if tackle_score >= current_min_target_eval * 0.3: 
                                opponents_to_consider.append({'bot': opp_obj, 'dist': opp_dist, 'score': tackle_score})
            
            if opponents_to_consider:
                opponents_to_consider.sort(key=lambda x: (-x['score'], x['dist']))
                chosen_opponent_to_tackle = opponents_to_consider[0]['bot']
                if position_equals(current_pos, chosen_opponent_to_tackle.position): self.goal_position = None
                else:
                    self.goal_position = chosen_opponent_to_tackle.position
                    self.current_target_is_teleporter_entry = False
                    final_dx, final_dy = get_direction(current_pos.x, current_pos.y, self.goal_position.x, self.goal_position.y)
                    return final_dx, final_dy 
        
        # --- 6. Finalize Goal to Base if no good target ---
        # (Kondisi ini juga menangani kasus 4 diamond di tas, waktu masih banyak, tapi tidak ada target lain yang bagus)
        if not self.goal_position or \
           (best_diamond_data and best_diamond_data['score'] < current_min_target_eval and \
            not use_red_button_action and not opponents_to_consider): 
            if diamonds_held > 0 : 
                 self.goal_position = path_target_base 
                 self.current_target_is_teleporter_entry = use_tp_base and \
                    (path_target_base is not None and not position_equals(path_target_base, my_base))
                 if self.goal_position and not position_equals(current_pos, self.goal_position):
                    final_dx, final_dy = get_direction(current_pos.x, current_pos.y, self.goal_position.x, self.goal_position.y)
                 elif self.goal_position and position_equals(current_pos, self.goal_position) and self.current_target_is_teleporter_entry:
                    final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board)
                 else: 
                    final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board)
        
        # --- Fallback ---
        if final_dx == 0 and final_dy == 0: 
            final_dx, final_dy = self._get_safe_random_move_or_cycle(current_pos, board)
            
        return final_dx, final_dy
