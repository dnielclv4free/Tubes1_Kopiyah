import random
from typing import Optional, Tuple, List, Dict, cast

from game.logic.base import BaseLogic
from game.models import GameObject, Board, Position, Properties #
from game.util import get_direction #

DEFAULT_TIME_PER_STEP_MS = 1000

class Dlogic(BaseLogic): #
    _TELEPORTER_TYPE_NAME = "TeleporterGameObject" #
    _RED_BUTTON_TYPE_NAME = "RedButtonGameObject" #

    # --- Konfigurasi Strategi ---
    HISTORY_LENGTH = 3 #
    ROAMING_DIRECTIONS = [(0, -1), (1, 0), (0, 1), (-1, 0)]  # N, E, S, W #
    
    
    STRATEGY_AVOID_AND_SAFE_DIAMOND_TIME_SECONDS = 18 # <<< BARU
    STRATEGY_MIN_DIAMONDS_FOR_AVOID = 3 
    STRATEGY_MAX_DIAMONDS_FOR_AVOID = 5 
    STRATEGY_SAFE_DIAMOND_RADIUS_MIN = 6 
    STRATEGY_SAFE_DIAMOND_RADIUS_MAX = 8 
    STRATEGY_AVOID_OPPONENT_RADIUS = 4 

    CRITICAL_TIME_RETURN_TO_BASE_SECONDS = 10 
    MIN_DIAMONDS_TO_PRIORITIZE_BASE_ON_CRITICAL_TIME = 1 #
    TACKLE_MODE_MAX_DIST_TO_OPPONENT = 7 #
    RESET_BUTTON_MAX_DIST_PREFERENCE = 5 #
    SAFE_TIME_BUFFER_STEPS = 3 #


    def __init__(self): #
        super().__init__()
        self.goal_position: Optional[Position] = None #
        self.current_roaming_direction_index = random.randint(0, len(self.ROAMING_DIRECTIONS) - 1) #
        self.position_history: List[Position] = [] #
        self.my_bot_id: Optional[int] = None #
        self.time_per_step_ms = DEFAULT_TIME_PER_STEP_MS #

    @staticmethod
    def _manhattan_distance(pos1: Position, pos2: Position) -> float: #
        return float(abs(pos1.x - pos2.x) + abs(pos1.y - pos2.y))

    @staticmethod
    def _position_equals(a: Optional[Position], b: Optional[Position]) -> bool: #
        if not a or not b:
            return a is b
        return a.x == b.x and a.y == b.y

    def _update_position_history(self, current_pos: Position): #
        if not self.position_history or not self._position_equals(self.position_history[-1], current_pos): #
            self.position_history.append(Position(x=current_pos.x, y=current_pos.y)) #
        if len(self.position_history) > self.HISTORY_LENGTH: #
            self.position_history.pop(0) #

    def _is_valid_pos(self, pos: Position, board_width: int, board_height: int) -> bool: #
        return 0 <= pos.x < board_width and 0 <= pos.y < board_height

    def _get_teleporter_pair_positions(self, board: Board) -> Optional[Tuple[Position, Position]]: #
        if not board.game_objects: return None
        teleporters = [
            obj.position
            for obj in board.game_objects
            if obj.type == self._TELEPORTER_TYPE_NAME and obj.position is not None
        ]
        if len(teleporters) == 2:
            pos1, pos2 = teleporters[0], teleporters[1]
            if pos1.x < pos2.x or (pos1.x == pos2.x and pos1.y < pos2.y):
                return pos1, pos2
            return pos2, pos1
        return None

    def _calculate_effective_distance_and_immediate_target( #
        self,
        start_pos: Position,
        end_pos: Position,
        tp_pair: Optional[Tuple[Position, Position]],
    ) -> Tuple[float, Position]:
        dist_direct = self._manhattan_distance(start_pos, end_pos) #
        best_dist = dist_direct #
        immediate_target = end_pos #

        if tp_pair: #
            tp1_pos, tp2_pos = tp_pair
            
            # Via TP1 -> TP2
            if not self._position_equals(start_pos, tp2_pos): #
                dist_to_tp1 = self._manhattan_distance(start_pos, tp1_pos) #
                dist_from_tp2_to_end = self._manhattan_distance(tp2_pos, end_pos) #
                dist_via_tp1 = dist_to_tp1 + 1 + dist_from_tp2_to_end #
                if dist_via_tp1 < best_dist: #
                    best_dist = dist_via_tp1 #
                    immediate_target = tp1_pos #

            # Via TP2 -> TP1
            if not self._position_equals(start_pos, tp1_pos): #
                dist_to_tp2 = self._manhattan_distance(start_pos, tp2_pos) #
                dist_from_tp1_to_end = self._manhattan_distance(tp1_pos, end_pos) #
                dist_via_tp2 = dist_to_tp2 + 1 + dist_from_tp1_to_end #
                if dist_via_tp2 < best_dist: #
                    best_dist = dist_via_tp2 #
                    immediate_target = tp2_pos #
        
        return best_dist, immediate_target

    def _get_roaming_move(self, current_pos: Position, board_width: int, board_height: int, preferred_target: Optional[Position] = None) -> Tuple[int, int]: #
        # Jika ada preferred_target (misal, menjauh dari lawan), coba ke sana dulu
        if preferred_target and not self._position_equals(current_pos, preferred_target):
            dx, dy = get_direction(current_pos.x, current_pos.y, preferred_target.x, preferred_target.y)
            next_pos_preferred = Position(x=current_pos.x + dx, y=current_pos.y + dy)
            if self._is_valid_pos(next_pos_preferred, board_width, board_height):
                return dx, dy

        valid_moves: List[Tuple[int, int]] = []
        preferred_moves: List[Tuple[int, int]] = []

        for i in range(len(self.ROAMING_DIRECTIONS)): #
            direction_idx = (self.current_roaming_direction_index + i) % len(self.ROAMING_DIRECTIONS) #
            dx, dy = self.ROAMING_DIRECTIONS[direction_idx] #
            next_pos = Position(x=current_pos.x + dx, y=current_pos.y + dy) #

            if self._is_valid_pos(next_pos, board_width, board_height): #
                valid_moves.append((dx, dy))
                is_in_history = any(self._position_equals(hist_pos, next_pos) for hist_pos in self.position_history) #
                if not is_in_history: #
                    preferred_moves.append((dx,dy))
                    if i == 0: #
                        self.current_roaming_direction_index = direction_idx #
                        return dx, dy
        
        if preferred_moves: #
            chosen_dx, chosen_dy = random.choice(preferred_moves)
            if (chosen_dx, chosen_dy) in self.ROAMING_DIRECTIONS:
                 self.current_roaming_direction_index = self.ROAMING_DIRECTIONS.index((chosen_dx, chosen_dy))
            return chosen_dx, chosen_dy

        if valid_moves: #
            chosen_dx, chosen_dy = random.choice(valid_moves)
            if (chosen_dx, chosen_dy) in self.ROAMING_DIRECTIONS:
                self.current_roaming_direction_index = self.ROAMING_DIRECTIONS.index((chosen_dx, chosen_dy))
            return chosen_dx, chosen_dy
        
        return 0, 0  #

    def _evaluate_diamond( #
        self, current_pos: Position, diamond_obj: GameObject, base_pos: Optional[Position],
        milliseconds_left: float, tp_pair: Optional[Tuple[Position, Position]],
        target_radius_from_base_min: Optional[int] = None, # BARU: parameter radius
        target_radius_from_base_max: Optional[int] = None  # BARU: parameter radius
    ) -> Optional[Dict[str, any]]:
        if not diamond_obj.position or not diamond_obj.properties: #
            return None
        
        diamond_pos = diamond_obj.position #

        
        if base_pos and target_radius_from_base_min is not None and target_radius_from_base_max is not None:
            dist_from_base = self._manhattan_distance(diamond_pos, base_pos)
            if not (target_radius_from_base_min <= dist_from_base <= target_radius_from_base_max):
                return None # Diamond tidak dalam radius yang diinginkan

        diamond_score = getattr(diamond_obj.properties, 'points', 1) #

        dist_to_diamond, immediate_target_to_diamond = self._calculate_effective_distance_and_immediate_target( #
            current_pos, diamond_pos, tp_pair
        )

        if dist_to_diamond == float('inf') or self._position_equals(current_pos, diamond_pos): #
            return None

        time_to_reach_diamond_ms = dist_to_diamond * self.time_per_step_ms #
        safe_buffer_ms = self.time_per_step_ms * self.SAFE_TIME_BUFFER_STEPS #

        if milliseconds_left != float('inf') and (time_to_reach_diamond_ms + safe_buffer_ms >= milliseconds_left): #
            return None

        total_trip_dist = dist_to_diamond #
        
        if base_pos: #
            dist_diamond_to_base, _ = self._calculate_effective_distance_and_immediate_target( #
                diamond_pos, base_pos, tp_pair
            )
            if dist_diamond_to_base == float('inf'): #
                return None 
            total_trip_dist += dist_diamond_to_base #
            
            time_for_full_run_ms = (dist_to_diamond + dist_diamond_to_base) * self.time_per_step_ms + (self.time_per_step_ms * 2) #
            if milliseconds_left != float('inf') and time_for_full_run_ms >= milliseconds_left: #
                return None
        
        return { #
            "actual_pos": diamond_pos,
            "immediate_target": immediate_target_to_diamond,
            "eff_dist_to_diamond": dist_to_diamond,
            "total_trip_estimate_dist": total_trip_dist,
            "diamond_score": diamond_score,
        }

    def _find_best_diamond_objective( #
        self, current_pos: Position, diamonds: List[GameObject], base_pos: Optional[Position],
        milliseconds_left: float, tp_pair: Optional[Tuple[Position, Position]],
        radius_min: Optional[int] = None, # BARU
        radius_max: Optional[int] = None  # BARU
    ) -> Optional[Dict[str, any]]:
        
        evaluated_candidates: List[Dict[str, any]] = [] #
        for d_obj in diamonds: #
            candidate_info = self._evaluate_diamond( #
                current_pos, d_obj, base_pos, milliseconds_left, tp_pair,
                target_radius_from_base_min=radius_min, # Teruskan parameter radius
                target_radius_from_base_max=radius_max
            )
            if candidate_info: #
                evaluated_candidates.append(candidate_info)
        
        if not evaluated_candidates: return None #

        evaluated_candidates.sort(key=lambda x: ( #
            x["total_trip_estimate_dist"] if base_pos else x["eff_dist_to_diamond"],
            -x["diamond_score"], #
            x["eff_dist_to_diamond"] #
        ))
        return evaluated_candidates[0] #

    def _find_threatening_opponent( # BARU: Fungsi untuk mencari lawan yang mengancam
        self, current_pos: Position, board_bots: List[GameObject],
        tp_pair: Optional[Tuple[Position, Position]], detection_radius: int
    ) -> Optional[Position]: # Mengembalikan posisi target untuk menghindar (menjauh)
        
        closest_threat_dist = float('inf')
        opponent_to_avoid_pos : Optional[Position] = None

        for bot_obj in board_bots: #
            if bot_obj.id == self.my_bot_id or not bot_obj.position: #
                continue
            
            opponent_actual_pos = cast(Position, bot_obj.position)
            eff_dist, _ = self._calculate_effective_distance_and_immediate_target( #
                current_pos, opponent_actual_pos, tp_pair
            )
            if eff_dist < detection_radius and eff_dist < closest_threat_dist :
                closest_threat_dist = eff_dist
                opponent_to_avoid_pos = opponent_actual_pos
        
        if opponent_to_avoid_pos: 
            return opponent_to_avoid_pos 
        return None

    def _get_avoid_move_target(self, current_pos: Position, opponent_pos: Position, board_width: int, board_height: int) -> Optional[Position]:
        """Mencari cell valid untuk bergerak menjauhi opponent_pos."""
        best_avoid_pos: Optional[Position] = None
        max_dist_from_opponent = -1

        for dx_check, dy_check in self.ROAMING_DIRECTIONS:
            avoid_candidate_pos = Position(x=current_pos.x + dx_check, y=current_pos.y + dy_check)
            if self._is_valid_pos(avoid_candidate_pos, board_width, board_height):
                dist = self._manhattan_distance(avoid_candidate_pos, opponent_pos)
                if dist > max_dist_from_opponent:
                    max_dist_from_opponent = dist
                    best_avoid_pos = avoid_candidate_pos
        return best_avoid_pos


    def _find_closest_opponent_with_diamonds( #
        self, current_pos: Position, board_bots: List[GameObject],
        tp_pair: Optional[Tuple[Position, Position]]
    ) -> Optional[Dict[str, any]]:
        
        best_opponent_info: Optional[Dict[str, any]] = None
        min_dist_to_opponent = float('inf') #

        for bot_obj in board_bots: #
            if bot_obj.id == self.my_bot_id or not bot_obj.position or not bot_obj.properties: #
                continue
            
            opponent_diamonds = getattr(bot_obj.properties, 'diamonds', 0) #
            opponent_pos = cast(Position, bot_obj.position) # Pasti ada karena cek di atas
            if opponent_diamonds > 0 : #
                eff_dist, immediate_target = self._calculate_effective_distance_and_immediate_target( #
                    current_pos, opponent_pos, tp_pair
                )
                if eff_dist < min_dist_to_opponent: #
                    min_dist_to_opponent = eff_dist #
                    best_opponent_info = {
                        "immediate_target": immediate_target,
                        "eff_dist": eff_dist
                    }
        return best_opponent_info

    def next_move(self, board_bot: GameObject, board: Board) -> Tuple[int, int]: #
        if self.my_bot_id is None and board_bot: #
            self.my_bot_id = board_bot.id #

        if not board_bot or not board_bot.position: #
            return self.ROAMING_DIRECTIONS[random.randint(0, len(self.ROAMING_DIRECTIONS) - 1)] #
            
        current_pos = board_bot.position #
        self._update_position_history(current_pos) #

        bot_props = board_bot.properties
        current_diamonds = getattr(bot_props, 'diamonds', 0) if bot_props else 0 #
        base_pos = getattr(bot_props, 'base', None) if bot_props else None #
        milliseconds_left = getattr(bot_props, 'milliseconds_left', float('inf')) if bot_props else float('inf') #
        
        inventory_size = 5 #
        if board.features: #
            inv_feature = next((f for f in board.features if f.name == "InventoryFeature" and f.config), None) #
            if inv_feature and hasattr(inv_feature.config, 'inventory_size') and inv_feature.config.inventory_size is not None: #
                inventory_size = inv_feature.config.inventory_size #
        elif bot_props and hasattr(bot_props, 'inventory_size') and bot_props.inventory_size is not None: #
             inventory_size = bot_props.inventory_size #

        self.time_per_step_ms = board.minimum_delay_between_moves if board.minimum_delay_between_moves is not None and board.minimum_delay_between_moves > 0 else DEFAULT_TIME_PER_STEP_MS #
        
        tp_pair = self._get_teleporter_pair_positions(board) #
        red_button_pos: Optional[Position] = None #
        if board.game_objects: #
            for obj in board.game_objects: #
                if obj.type == self._RED_BUTTON_TYPE_NAME and obj.position: #
                    red_button_pos = obj.position #
                    break
        
        all_diamonds = board.diamonds if board.diamonds else [] #
        board_bots_list = board.bots if board.bots else [] #

        self.goal_position = None #
        is_full = current_diamonds >= inventory_size #
        
        
        in_avoid_and_safe_diamond_mode = \
            (self.STRATEGY_MIN_DIAMONDS_FOR_AVOID <= current_diamonds <= self.STRATEGY_MAX_DIAMONDS_FOR_AVOID) and \
            (milliseconds_left <= self.STRATEGY_AVOID_AND_SAFE_DIAMOND_TIME_SECONDS * 1000)

        opponent_to_avoid_target: Optional[Position] = None

        if in_avoid_and_safe_diamond_mode:
            # 1. Cek lawan yang mengancam untuk dihindari
            threatening_opponent_actual_pos = self._find_threatening_opponent(
                current_pos, board_bots_list, tp_pair, self.STRATEGY_AVOID_OPPONENT_RADIUS
            )
            if threatening_opponent_actual_pos:
                # Cari cell terbaik untuk menjauh
                opponent_to_avoid_target = self._get_avoid_move_target(current_pos, threatening_opponent_actual_pos, board.width, board.height)
                if opponent_to_avoid_target: # Jika ada cell valid untuk menghindar
                    self.goal_position = opponent_to_avoid_target
                # Jika tidak ada cell valid untuk menghindar (misal terjebak), biarkan goal_position None,
                # akan ditangani oleh logika roaming/pulang nanti, atau prioritas lain.


            # 2. Jika tidak ada ancaman langsung atau tidak bisa menghindar, cari diamond dekat base
            if self.goal_position is None and base_pos:
                best_safe_diamond = self._find_best_diamond_objective(
                    current_pos, all_diamonds, base_pos, milliseconds_left, tp_pair,
                    radius_min=self.STRATEGY_SAFE_DIAMOND_RADIUS_MIN,
                    radius_max=self.STRATEGY_SAFE_DIAMOND_RADIUS_MAX
                )
                if best_safe_diamond:
                    self.goal_position = best_safe_diamond["immediate_target"]
            
            # 3. Jika tidak ada diamond aman & masih dalam mode ini & bawa diamond, pulang ke base
            if self.goal_position is None and current_diamonds > 0 and base_pos and not self._position_equals(current_pos, base_pos):
                 _, immediate_target_to_base = self._calculate_effective_distance_and_immediate_target( #
                    current_pos, base_pos, tp_pair
                )
                 self.goal_position = immediate_target_to_base


        # Jika tidak dalam mode strategi khusus atau mode khusus tidak menghasilkan goal_position
        if self.goal_position is None:
            # PRIORITAS 1: Kembali ke base jika penuh atau waktu kritis (setelah strategi baru)
            if base_pos: #
                dist_to_base, immediate_target_to_base = self._calculate_effective_distance_and_immediate_target( #
                    current_pos, base_pos, tp_pair
                )
                # Menggunakan CRITICAL_TIME_RETURN_TO_BASE_SECONDS yang sudah disesuaikan
                time_to_return_ms = (dist_to_base * self.time_per_step_ms) + (self.time_per_step_ms * self.SAFE_TIME_BUFFER_STEPS) #
                critical_time_standard_ms = self.CRITICAL_TIME_RETURN_TO_BASE_SECONDS * 1000

                should_return_to_base_standard = is_full or \
                                        (milliseconds_left <= critical_time_standard_ms and \
                                        current_diamonds >= self.MIN_DIAMONDS_TO_PRIORITIZE_BASE_ON_CRITICAL_TIME and \
                                        milliseconds_left != float('inf') and \
                                        time_to_return_ms < milliseconds_left) #

                if should_return_to_base_standard and not self._position_equals(current_pos, base_pos): #
                    self.goal_position = immediate_target_to_base #
            
            # PRIORITAS 2: Strategi lain jika tidak pulang (setelah strategi baru)
            if self.goal_position is None: #
                best_diamond_obj_general = self._find_best_diamond_objective( #
                    current_pos, all_diamonds, base_pos, milliseconds_left, tp_pair
                ) # Tanpa filter radius
                dist_to_closest_diamond_general = best_diamond_obj_general["eff_dist_to_diamond"] if best_diamond_obj_general else float('inf') #

                # 2a. Mode Tackle
                if current_diamonds == 0: #
                    opponent_info = self._find_closest_opponent_with_diamonds( #
                        current_pos, board_bots_list, tp_pair
                    )
                    if opponent_info and opponent_info["eff_dist"] < dist_to_closest_diamond_general and \
                       opponent_info["eff_dist"] <= self.TACKLE_MODE_MAX_DIST_TO_OPPONENT: #
                        self.goal_position = opponent_info["immediate_target"] #

                # 2b. Mode Reset Button
                if self.goal_position is None and red_button_pos: #
                    dist_to_rb, immediate_target_to_rb = self._calculate_effective_distance_and_immediate_target( #
                        current_pos, red_button_pos, tp_pair
                    )
                    if dist_to_rb < dist_to_closest_diamond_general and dist_to_rb <= self.RESET_BUTTON_MAX_DIST_PREFERENCE: #
                        time_to_reach_rb_ms = dist_to_rb * self.time_per_step_ms + self.time_per_step_ms #
                        if milliseconds_left == float('inf') or time_to_reach_rb_ms < milliseconds_left: #
                            self.goal_position = immediate_target_to_rb #
                
                # 2c. Diamond Hunting Umum
                if self.goal_position is None and current_diamonds < inventory_size and best_diamond_obj_general: #
                    self.goal_position = best_diamond_obj_general["immediate_target"] #

                # 2d. Fallback pulang jika bawa diamond (umum)
                if self.goal_position is None and current_diamonds > 0 and base_pos and \
                   not self._position_equals(current_pos, base_pos): #
                    # Gunakan dist_to_base dan immediate_target_to_base yang sudah dihitung di awal blok ini
                    if 'immediate_target_to_base' in locals() and immediate_target_to_base:
                        self.goal_position = immediate_target_to_base
                    else: # Hitung ulang jika belum ada (seharusnya jarang terjadi)
                        _, immediate_target_to_base_fallback = self._calculate_effective_distance_and_immediate_target( #
                            current_pos, base_pos, tp_pair)
                        self.goal_position = immediate_target_to_base_fallback #

        # --- Penentuan Gerakan Akhir ---
        delta_x, delta_y = 0, 0 #
        
        # Jika target adalah menghindar dari lawan, gunakan _get_roaming_move dengan preferensi menjauh
        if opponent_to_avoid_target and self.goal_position == opponent_to_avoid_target : # Periksa apakah goal_position diset untuk menghindar
             
             if self.goal_position and not self._position_equals(current_pos, self.goal_position):
                delta_x, delta_y = get_direction(current_pos.x, current_pos.y, self.goal_position.x, self.goal_position.y)
             else: # Jika sudah di posisi menghindar (atau tidak ada), roam biasa.
                delta_x, delta_y = self._get_roaming_move(current_pos, board.width, board.height)


        elif self.goal_position: #
            is_at_red_button_and_goal = red_button_pos and \
                                        self._position_equals(current_pos, red_button_pos) and \
                                        self._position_equals(self.goal_position, red_button_pos) #
            is_at_base_and_full_and_goal = base_pos and \
                                           self._position_equals(current_pos, base_pos) and \
                                           self._position_equals(self.goal_position, base_pos) and \
                                           is_full #

            if self._position_equals(current_pos, self.goal_position) and \
               not (is_at_red_button_and_goal or is_at_base_and_full_and_goal): #
                delta_x, delta_y = self._get_roaming_move(current_pos, board.width, board.height) #
            else:
                delta_x, delta_y = get_direction( #
                    current_pos.x, current_pos.y,
                    self.goal_position.x, self.goal_position.y
                )
        else: 
            delta_x, delta_y = self._get_roaming_move(current_pos, board.width, board.height) #

        if delta_x == 0 and delta_y == 0: #
            is_on_red_button_intentional = red_button_pos and self._position_equals(current_pos, red_button_pos) and \
                                           (self.goal_position and self._position_equals(self.goal_position, red_button_pos)) #
            is_at_base_full_intentional = base_pos and self._position_equals(current_pos, base_pos) and is_full and \
                                          (self.goal_position and self._position_equals(self.goal_position, base_pos)) #

            if not (is_on_red_button_intentional or is_at_base_full_intentional): #
                 roaming_dx, roaming_dy = self._get_roaming_move(current_pos, board.width, board.height) #
                 if roaming_dx == 0 and roaming_dy == 0: #
                    for i in range(len(self.ROAMING_DIRECTIONS)):
                        test_idx = (self.current_roaming_direction_index + 1 + i) % len(self.ROAMING_DIRECTIONS)
                        forced_dx, forced_dy = self.ROAMING_DIRECTIONS[test_idx]
                        if self._is_valid_pos(Position(x=current_pos.x + forced_dx, y=current_pos.y + forced_dy), board.width, board.height):
                            self.current_roaming_direction_index = test_idx
                            delta_x, delta_y = forced_dx, forced_dy
                            break 
                 else:
                    delta_x, delta_y = roaming_dx, roaming_dy #
            
        return delta_x, delta_y

    
    def get_move_to_target(self, current_point: Position, target_point: Position) -> Optional[str]: #
        dx = target_point.x - current_point.x
        dy = target_point.y - current_point.y

        if dx == 1 and dy == 0: return "r"
        elif dx == -1 and dy == 0: return "l"
        elif dx == 0 and dy == 1: return "u" 
        elif dx == 0 and dy == -1: return "d" 
        return None
