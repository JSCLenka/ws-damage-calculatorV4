import streamlit as st
import random
import json
import os

# ==========================================
# 0. CX (高潮卡) 触发类型配置库
# ==========================================
CX_TYPES = {
    "Comeback (Door)": {"soul": 0, "effect": "comeback"},
    "Pool (Bag)": {"soul": 0, "effect": "pool"},
    "Draw (Book)": {"soul": 0, "effect": "draw"},
    "Treasure (Bar)": {"soul": 0, "effect": "treasure"},
    "Choice": {"soul": 0, "effect": "choice"},
    "Discovery": {"soul": 0, "effect": "discovery"},
    "Chance": {"soul": 0, "effect": "chance"},
    "Return (Wind)": {"soul": 1, "effect": "return"},
    "Gate": {"soul": 1, "effect": "gate"},
    "Standby": {"soul": 1, "effect": "standby"},
    "Shot": {"soul": 1, "effect": "shot"},
    "2 Souls": {"soul": 2, "effect": "none"}
}

CX_OPTIONS = list(CX_TYPES.keys())

# ==========================================
# 1. 核心游戏引擎 (纯粹的物理与状态机)
# ==========================================
class Card:
    def __init__(self, name, level=0, image="", code="", soul=0):
        self.name = name
        self.level = level
        self.image = image
        self.code = code
        self.soul = soul
        self.effects = []
        self.has_shot_trigger = False
        self.last_cancelled_amount = 0  # 记录刚刚被取消的伤害

class Effect:
    def __init__(self, trigger, action_func, max_uses=99):
        self.trigger = trigger
        self.action_func = action_func
        self.max_uses = max_uses
        self.current_uses = 0

class GameEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.force_trigger = cfg.get("p_force_trigger", False)
        self.all_active_cards = []
        
        # --- 1. 构建对手场面与资源 ---
        self.opp_stock = cfg.get("o_stock", 0)
        self.opp_hand = cfg.get("o_hand", 0)
        self.opp_memory = cfg.get("o_memory", 0)
        self.opp_front = cfg.get("o_front", 0)
        self.opp_back = cfg.get("o_back", 0)
        
        self.opp_deck = []
        self.opp_waiting_room = []
        self.opp_clock_zone = []

        if cfg.get("o_advanced", False):
            self.opp_level = cfg["o_lvl_adv"]
            # 构建 WR
            self.opp_waiting_room.extend([{"is_cx": False, "level": 3, "trigger": True} for _ in range(cfg["o_wr_l3"])])
            self.opp_waiting_room.extend([{"is_cx": False, "level": 2, "trigger": True} for _ in range(cfg["o_wr_l2"])])
            self.opp_waiting_room.extend([{"is_cx": False, "level": 1, "trigger": False} for _ in range(cfg["o_wr_l1"])])
            self.opp_waiting_room.extend([{"is_cx": False, "level": 0, "trigger": False} for _ in range(cfg["o_wr_l0"])])
            self.opp_waiting_room.extend([{"is_cx": False, "level": 2, "trigger": False} for _ in range(cfg["o_wr_l2e"])])
            self.opp_waiting_room.extend([{"is_cx": True, "level": 0, "cx_type": cfg["o_wr_cx1_type"]} for _ in range(cfg["o_wr_cx1"])])
            self.opp_waiting_room.extend([{"is_cx": True, "level": 0, "cx_type": cfg["o_wr_cx2_type"]} for _ in range(cfg["o_wr_cx2"])])
            # 构建 Clock
            self.opp_clock_zone.extend([{"is_cx": False, "level": 3, "trigger": True} for _ in range(cfg["o_clk_l3"])])
            self.opp_clock_zone.extend([{"is_cx": False, "level": 2, "trigger": True} for _ in range(cfg["o_clk_l2"])])
            self.opp_clock_zone.extend([{"is_cx": False, "level": 1, "trigger": False} for _ in range(cfg["o_clk_l1"])])
            self.opp_clock_zone.extend([{"is_cx": False, "level": 0, "trigger": False} for _ in range(cfg["o_clk_l0"])])
            self.opp_clock_zone.extend([{"is_cx": False, "level": 2, "trigger": False} for _ in range(cfg["o_clk_l2e"])])
            self.opp_clock_zone.extend([{"is_cx": True, "level": 0, "cx_type": cfg["o_clk_cx1_type"]} for _ in range(cfg["o_clk_cx1"])])
            self.opp_clock_zone.extend([{"is_cx": True, "level": 0, "cx_type": cfg["o_clk_cx2_type"]} for _ in range(cfg["o_clk_cx2"])])
            # 构建 Deck
            self.opp_deck.extend([{"is_cx": True, "level": 0, "cx_type": cfg["o_dk_cx1_type"]} for _ in range(cfg["o_dk_cx1"])])
            self.opp_deck.extend([{"is_cx": True, "level": 0, "cx_type": cfg["o_dk_cx2_type"]} for _ in range(cfg["o_dk_cx2"])])
            pad_count = max(0, cfg["o_dk_total"] - len(self.opp_deck))
            self.opp_deck.extend([{"is_cx": False, "level": random.randint(0, 3), "trigger": False} for _ in range(pad_count)])
        else:
            self.opp_level = cfg.get("o_lvl", 3)
            for _ in range(cfg.get("o_clk", 0)): self.opp_clock_zone.append({"is_cx": False, "level": 0, "trigger": False})
            self.opp_deck.extend([{"is_cx": True, "level": 0, "cx_type": "Comeback (Door)"} for _ in range(cfg.get("o_cx", 8))])
            pad_count = max(0, cfg.get("o_deck", 30) - cfg.get("o_cx", 8))
            self.opp_deck.extend([{"is_cx": False, "level": random.randint(0, 3), "trigger": False} for _ in range(pad_count)])
            
        random.shuffle(self.opp_deck)

        # --- 2. 构建玩家场面与资源 ---
        self.player_stock = cfg.get("p_stock", 0)
        self.player_hand = cfg.get("p_hand", 0)
        self.player_memory = cfg.get("p_memory", 0)
        self.player_deck = []
        self.player_waiting_room = []
        self.player_clock_zone = []
        
        if cfg.get("p_advanced", False):
            self.player_waiting_room.extend([{"is_cx": False, "level": 3, "trigger": True} for _ in range(cfg["p_wr_l3"])])
            self.player_waiting_room.extend([{"is_cx": False, "level": 2, "trigger": True} for _ in range(cfg["p_wr_l2"])])
            self.player_waiting_room.extend([{"is_cx": False, "level": 1, "trigger": False} for _ in range(cfg["p_wr_l1"])])
            self.player_waiting_room.extend([{"is_cx": False, "level": 0, "trigger": False} for _ in range(cfg["p_wr_l0"])])
            self.player_waiting_room.extend([{"is_cx": False, "level": 2, "trigger": False} for _ in range(cfg["p_wr_l2e"])])
            self.player_waiting_room.extend([{"is_cx": True, "level": 0, "cx_type": cfg["p_wr_cx1_type"]} for _ in range(cfg["p_wr_cx1"])])
            self.player_waiting_room.extend([{"is_cx": True, "level": 0, "cx_type": cfg["p_wr_cx2_type"]} for _ in range(cfg["p_wr_cx2"])])
            
            self.player_clock_zone.extend([{"is_cx": False, "level": 3, "trigger": True} for _ in range(cfg["p_clk_l3"])])
            self.player_clock_zone.extend([{"is_cx": False, "level": 2, "trigger": True} for _ in range(cfg["p_clk_l2"])])
            self.player_clock_zone.extend([{"is_cx": False, "level": 1, "trigger": False} for _ in range(cfg["p_clk_l1"])])
            self.player_clock_zone.extend([{"is_cx": False, "level": 0, "trigger": False} for _ in range(cfg["p_clk_l0"])])
            self.player_clock_zone.extend([{"is_cx": False, "level": 2, "trigger": False} for _ in range(cfg["p_clk_l2e"])])
            self.player_clock_zone.extend([{"is_cx": True, "level": 0, "cx_type": cfg["p_clk_cx1_type"]} for _ in range(cfg["p_clk_cx1"])])
            self.player_clock_zone.extend([{"is_cx": True, "level": 0, "cx_type": cfg["p_clk_cx2_type"]} for _ in range(cfg["p_clk_cx2"])])
            
            self.player_deck.extend([{"is_cx": False, "level": 3, "trigger": True} for _ in range(cfg["p_dk_l3"])])
            self.player_deck.extend([{"is_cx": False, "level": 2, "trigger": True} for _ in range(cfg["p_dk_l2"])])
            self.player_deck.extend([{"is_cx": False, "level": 1, "trigger": False} for _ in range(cfg["p_dk_l1"])])
            self.player_deck.extend([{"is_cx": False, "level": 0, "trigger": False} for _ in range(cfg["p_dk_l0"])])
            self.player_deck.extend([{"is_cx": False, "level": 2, "trigger": False} for _ in range(cfg["p_dk_l2e"])])
            self.player_deck.extend([{"is_cx": True, "level": 0, "trigger": False, "cx_type": cfg["p_dk_cx1_type"]} for _ in range(cfg["p_dk_cx1"])])
            self.player_deck.extend([{"is_cx": True, "level": 0, "trigger": False, "cx_type": cfg["p_dk_cx2_type"]} for _ in range(cfg["p_dk_cx2"])])
            pad_count = max(0, cfg["p_dk_total"] - len(self.player_deck))
            self.player_deck.extend([{"is_cx": False, "level": 0, "trigger": False} for _ in range(pad_count)])
        else:
            self.player_deck.extend([{"is_cx": True, "level": 0, "trigger": False, "cx_type": cfg["p_dk_cx1_type"]} for _ in range(cfg["p_dk_cx1"])])
            self.player_deck.extend([{"is_cx": True, "level": 0, "trigger": False, "cx_type": cfg["p_dk_cx2_type"]} for _ in range(cfg["p_dk_cx2"])])
            pad_count = max(0, cfg["p_deck"] - cfg["p_dk_cx1"] - cfg["p_dk_cx2"])
            for i in range(pad_count):
                self.player_deck.append({"is_cx": False, "level": random.randint(0, 3), "trigger": i < cfg.get("p_trig", 6)})
        
        random.shuffle(self.player_deck)

    # ----------------------------------------------------
    # 底层物理动作库 (洗牌、伤害、升级机制)
    # ----------------------------------------------------
    def _process_level_up(self, clock_zone, waiting_room):
        """处理升级：优先挑一张不是 CX 的卡去升级，剩下的进休息室"""
        chosen_idx = 0
        for i, card in enumerate(clock_zone):
            if not card.get("is_cx", False):
                chosen_idx = i
                break
        clock_zone.pop(chosen_idx)
        waiting_room.extend(clock_zone)
        clock_zone.clear()

    def player_refresh(self):
        """玩家侧洗牌与罚血逻辑"""
        if not self.player_waiting_room: return
        self.player_deck = self.player_waiting_room.copy()
        random.shuffle(self.player_deck)
        self.player_waiting_room = []
        
        if self.cfg.get("p_advanced", False):
            if self.player_deck:
                self.player_clock_zone.append(self.player_deck.pop(0))
            if len(self.player_clock_zone) >= 7:
                self._process_level_up(self.player_clock_zone, self.player_waiting_room)

    def refresh_opp(self):
        """对手侧洗牌与罚血逻辑"""
        if not self.opp_waiting_room: return
        self.opp_deck = self.opp_waiting_room.copy()
        random.shuffle(self.opp_deck)
        self.opp_waiting_room = []
        self.take_damage(1) 

    def take_damage(self, amount):
        """强制进血 (用于对手洗牌罚血)"""
        for _ in range(amount):
            if not self.opp_deck:
                self.refresh_opp()
            if self.opp_deck:
                self.opp_clock_zone.append(self.opp_deck.pop(0)) 
            if len(self.opp_clock_zone) >= 7:
                self.opp_level += 1
                self._process_level_up(self.opp_clock_zone, self.opp_waiting_room)

    def deal_damage(self, amount, source_card=None):
        """常规攻击烧血 (可被 CX 取消)"""
        if amount <= 0: return True
        res_zone = []
        is_cancelled = False
        
        for _ in range(amount):
            if not self.opp_deck: self.refresh_opp()
            if not self.opp_deck: break
            
            card = self.opp_deck.pop(0)
            res_zone.append(card)
            
            if card["is_cx"]:
                is_cancelled = True
                break
        
        if is_cancelled:
            print(f"  🛡️ [伤害结果] 翻出 CX！ 发起的 {amount} 点伤害被【取消】。")
            self.opp_waiting_room.extend(res_zone)
            if source_card:
                # 🌟 记录刚刚被取消的伤害数值
                source_card.last_cancelled_amount = amount 
                self.check_triggers("OnDamageCancel", source_card)
            return False
        else:
            print(f"  🩸 [伤害结果] 没翻出 CX！ 发起的 {amount} 点伤害被【吃下】！")
            for card in res_zone:
                self.opp_clock_zone.append(card)
                if len(self.opp_clock_zone) >= 7:
                    self.opp_level += 1
                    self._process_level_up(self.opp_clock_zone, self.opp_waiting_room)
            return True

    def trigger_step(self, attacker):
        """判卡判定"""
        if not self.player_deck: self.player_refresh()
        if not self.player_deck: return 0
        
        card = self.player_deck.pop(0)
        if not self.player_deck: self.player_refresh()

        wr_has_cards = len(self.player_waiting_room) > 0
        
        if card["is_cx"]:
            cx_info = CX_TYPES.get(card.get("cx_type", "Comeback (Door)"), {"soul": 0, "effect": "none"})
            effect = cx_info["effect"]
            
            if effect == "pool":         
                self.player_stock += 1
            elif effect == "comeback" and wr_has_cards:   
                self.player_hand += 1
            elif effect == "draw":       
                self.player_hand += 1
            elif effect == "treasure":   
                self.player_hand += 1
                self.player_stock += 1
            elif effect == "choice" and wr_has_cards:     
                if random.random() < 0.5: self.player_hand += 1
                else: self.player_stock += 1
            elif effect == "discovery":  
                self.player_hand += 1
                for _ in range(min(2, len(self.player_deck))):
                    self.player_waiting_room.append(self.player_deck.pop(0))
            elif effect == "chance":     
                self.player_hand += 1
                self.player_stock += 1
                for _ in range(min(1, len(self.player_deck))):
                    self.player_waiting_room.append(self.player_deck.pop(0))
            elif effect == "return":     
                if self.opp_front > 0:
                    self.opp_front -= 1
                    self.opp_hand += 1
                elif self.opp_back > 0:
                    self.opp_back -= 1
                    self.opp_hand += 1
            elif effect == "gate" and wr_has_cards:       
                self.player_hand += 1
            elif effect == "shot":       
                attacker.has_shot_trigger = True
            
            self.player_stock += 1 
            return cx_info["soul"]
        else:
            self.player_stock += 1
            return 1 if card.get("trigger") else 0

    def simulate_attack(self, attacker):
        """执行单次攻击完整流程"""
        self.check_triggers("OnAttack", attacker)
        attacker.has_shot_trigger = False 
        
        is_direct_attack = False
        if self.opp_front > 0:
            self.opp_front -= 1
        else:
            is_direct_attack = True

        trigger_soul = self.trigger_step(attacker)
        total_soul = attacker.soul + trigger_soul + (1 if is_direct_attack else 0)
        
        direct_msg = " (空场+1)" if is_direct_attack else ""
        print(f"  🗡️ [基础攻击] 基础{attacker.soul}魂 + 触发{trigger_soul}魂{direct_msg} = 发起 {total_soul} 点伤害！")
        
        is_damage_resolved = self.deal_damage(total_soul, source_card=attacker)
        
        if not is_damage_resolved and getattr(attacker, "has_shot_trigger", False):
            print(f"  🔥 [触发补刀] 伤害被取消！发动 Shot Trigger 补刀 1 伤！")
            self.deal_damage(1, source_card=None)

    def check_triggers(self, trigger_type, current_card=None):
        """事件监听与广播"""
        for card in self.all_active_cards:
            for eff in card.effects:
                if eff.trigger == trigger_type:
                    # 🌟 加上 OnDamageCancel，确保谁被取消了，谁才触发！
                    if trigger_type in ["OnAttack", "OnPlay", "OnCancel", "OnDamageCancel"]:
                        if card != current_card: continue 
                    if trigger_type in ["OnOtherAttack", "OnOtherPlay"]:
                        if card == current_card: continue

                    if eff.current_uses < eff.max_uses:
                        eff.current_uses += 1
                        eff.action_func(self, card)

    # ----------------------------------------------------
    # 抽象语法树 (AST) 解释器与数学计算中心
    # ----------------------------------------------------
    def evaluate_condition(self, cond):
        """通用战局条件解析器：执行嵌套算术与逻辑运算"""
        # 🌟 新增：如果开启了上帝模式，无视任何条件直接返回 True
        if getattr(self, "force_trigger", False):
            return True

        if not cond: return True
        
        if "operator" in cond:
            op = cond["operator"]
            if op == "AND":
                return all(self.evaluate_condition(c) for c in cond.get("conditions", []))
            elif op == "OR":
                return any(self.evaluate_condition(c) for c in cond.get("conditions", []))

        target = cond.get("target")
        cmp = cond.get("cmp", "==")
        value = cond.get("value", 0)

        actual_val = 0
        if target == "opp_level": actual_val = getattr(self, "opp_level", 0)
        elif target == "opp_clock": actual_val = len(getattr(self, "opp_clock_zone", []))
        elif target == "my_level": actual_val = getattr(self, "player_level", 0)
        elif target == "opp_stock": actual_val = getattr(self, "opp_stock", 0)
        elif target == "player_hand": actual_val = getattr(self, "player_hand", 0)

        if cmp == "==": return actual_val == value
        elif cmp == ">=": return actual_val >= value
        elif cmp == "<=": return actual_val <= value
        elif cmp == ">": return actual_val > value
        elif cmp == "<": return actual_val < value

        return False

    def mill_and_check_player_top(self, condition):
        """独立的基础推顶指令助手 (为了适配 CheckCondition 指令)"""
        if not self.player_deck: self.player_refresh()
        if not self.player_deck: return False
        
        top_card = self.player_deck.pop(0)
        self.player_waiting_room.append(top_card)
        
        if condition == "soul":
            return top_card.get("trigger", False)
        elif condition == "cx":
            return top_card.get("is_cx", False)
        return False

    def execute_instructions(self, instructions, source_card):
        """完全解耦的 JSON 积木执行器"""
        if not instructions: return

        for inst in instructions:
            op = inst.get("op")
            
            if op == "DealDamage":
                amount = inst.get("amount", 1)
                
                # 🌟 如果伤害值是 "last_cancelled"，则动态读取
                if amount == "last_cancelled":
                    amount = getattr(source_card, "last_cancelled_amount", 0)
                
                print(f"👉 [技能执行] {source_card.name} 发动效果，造成 {amount} 点伤害")
                self.deal_damage(amount, source_card=source_card)
                
            elif op == "Heal":
                amount = inst.get("amount", 1)
                for _ in range(amount):
                    if getattr(self, "player_clock_zone", []):
                        self.player_waiting_room.append(self.player_clock_zone.pop())

            # ==========================================
            # 🌟 新增指令：处理对手区资源互换 (洗费/洗坟)
            elif op == "StockSwap":
                stock_count = getattr(self, "opp_stock", 0)
                if stock_count > 0:
                    print(f"  🌪️ [效果执行] {source_card.name} 发动效果：将对方 {stock_count} 张 Stock 全部放置到休息室，并从牌组顶放置同等数量的卡牌！")
                    self.opp_stock = 0
                    for _ in range(stock_count):
                        if not self.opp_deck: self.refresh_opp()
                        if self.opp_deck:
                            self.opp_waiting_room.append(self.opp_deck.pop(0))
                    self.opp_stock = stock_count
                    
            elif op == "ReverseShuffle":
                amount = inst.get("amount", 3)
                print(f"  🌀 [效果执行] {source_card.name} 发动效果：将对方休息室最多 {amount} 张卡牌洗回牌组！")
                cards_to_return = []
                for _ in range(min(amount, len(self.opp_waiting_room))):
                    cards_to_return.append(self.opp_waiting_room.pop())
                self.opp_deck.extend(cards_to_return)
                random.shuffle(self.opp_deck)
            # ==========================================
                        
            elif op == "CheckCondition":
                zone = inst.get("zone")
                action = inst.get("action")
                condition = inst.get("condition")
                
                if zone == "player_deck" and action == "mill":
                    deck_before = len(self.player_deck)
                    success = self.mill_and_check_player_top(condition)
                    print(f"🎲 [推顶判定] 目标: {condition} (余牌 {deck_before}) -> 结果: {'✅ 成功' if success else '❌ 失败'}")
                    
                    if success: self.execute_instructions(inst.get("on_true", []), source_card)
                    else: self.execute_instructions(inst.get("on_false", []), source_card)

            elif op == "IfGameState":
                cond_obj = inst.get("condition", {})
                is_met = self.evaluate_condition(cond_obj)
                
                if is_met:
                    print(f"  🧠 [战术抉择] JSON复合条件满足！执行分支 A (True)")
                    self.execute_instructions(inst.get("on_true", []), source_card)
                else:
                    print(f"  🧠 [战术抉择] JSON复合条件不满足，执行分支 B (False)")
                    self.execute_instructions(inst.get("on_false", []), source_card)

            elif op == "MoveCard":
                src = inst.get("src")
                dest = inst.get("dest")
                amount = inst.get("amount", 1)
                print(f"  📦 [物理转移] 尝试从 {src} 移动 {amount} 张卡到 {dest}")
                
                if src == "opp_clock" and dest == "opp_level":
                    if hasattr(self, "opp_level") and getattr(self, "opp_clock_zone", []):
                        self.opp_level += 1 
                
                elif src == "opp_clock" and dest == "opp_waiting_room":
                    if hasattr(self, "opp_clock_zone") and hasattr(self, "opp_waiting_room"):
                        if amount == "all":
                            self.opp_waiting_room.extend(self.opp_clock_zone)
                            self.opp_clock_zone.clear()
                        else:
                            for _ in range(min(amount, len(self.opp_clock_zone))):
                                self.opp_waiting_room.append(self.opp_clock_zone.pop(0))

            elif op == "FilterDeck":
                pass

            # ==========================================
            # 🌟 修复 4：超级嵌套逻辑 —— 贴膜/赋予技能
            elif op == "GiveEffect":
                target_type = inst.get("target", "any_character")
                
                # 智能贴膜寻敌逻辑 (左 -> 中 -> 右)
                targets = []
                if target_type == "other_character":
                    front_row = self.all_active_cards[:3] 
                    my_idx = front_row.index(source_card) if source_card in front_row else -1
                    
                    if my_idx != -1:
                        for i in range(my_idx + 1, len(front_row)):
                            if front_row[i] != source_card:
                                targets.append(front_row[i])
                                
                        if not targets:
                            for i in range(0, my_idx):
                                if front_row[i] != source_card:
                                    targets.append(front_row[i])
                                    
                    if not targets:
                        targets = [c for c in self.all_active_cards if c != source_card]
                else:
                    targets = [source_card]
                
                if not targets: continue
                target_card = targets[0] # 取最优解顺位
                
                # 处理魂加成
                if "soul_boost" in inst:
                    boost = inst.get("soul_boost", 0)
                    target_card.soul += boost
                    print(f"  ✨ [Buff赋予] {source_card.name} 给 {target_card.name} 魂+{boost}！")

                # 处理技能贴膜 (嵌套解析)
                new_eff_json = inst.get("effect")
                if new_eff_json:
                    trigger_name = new_eff_json.get("trigger")
                    limit = new_eff_json.get("limit", 1)
                    sub_instructions = new_eff_json.get("instructions", [])
                    
                    def make_instruction_action(inst_array):
                        return lambda eng, c, insts=inst_array: eng.execute_instructions(insts, c)
                        
                    target_card.effects.append(Effect(
                        trigger_name,
                        make_instruction_action(sub_instructions),
                        max_uses=limit
                    ))
                    print(f"  ✨ [技能贴膜] {source_card.name} 赋予了 {target_card.name} 技能 [{trigger_name}] (限{limit}次)！")       


# ==========================================
# 2. 数据处理：极简版卡牌构造器 (支持用户手动多选)
# ==========================================
@st.cache_data
def load_db():
    if not os.path.exists("cards.json"): 
        return {}
    try:
        with open("cards.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        db = {}
        for item in data:
            code = item.get("code", "???")
            name = item.get("name", "Unknown")
            display_key = f"[{code}] {name}"
            db[display_key] = item
        return db
    except Exception:
        return {}

RAW_DB = load_db()
CARD_OPTIONS = ["无 (Empty)"] + list(RAW_DB.keys())

def create_card_instance(display_key, soul, max_uses=99, user_choices=None):
    """
    现在支持多选卡片的分支注入！
    user_choices 格式例: { 1: 0, 2: 1 } (第2个效果选第0项，第3个效果选第1项)
    """
    if user_choices is None: user_choices = {}
    if display_key not in RAW_DB: 
        return None
    
    data = RAW_DB[display_key]
    
    card = Card(
        name=data.get("name", "Unknown"), 
        level=int(data.get("level", 0)), 
        image=data.get("image", ""), 
        code=data.get("code", ""), 
        soul=soul
    )
    
    for i, eff_data in enumerate(data.get("effects", [])):
        if isinstance(eff_data, dict):
            trigger_name = eff_data.get("trigger", "OnAttack")
            
            # 防死循环锁！
            if max_uses != 99:
                current_max_uses = max_uses 
            else:
                current_max_uses = eff_data.get("limit", 1) 
            
            # 🌟 动态抽取指令: 如果这是张多选卡，则抽取玩家在 UI 里选的那个战术分支
            if eff_data.get("is_choice"):
                choice_idx = user_choices.get(i, 0)
                choices_array = eff_data.get("choices", [])
                if choice_idx < len(choices_array):
                    instructions = choices_array[choice_idx].get("instructions", [])
                else:
                    instructions = []
            else:
                instructions = eff_data.get("instructions", [])
            
            def make_instruction_action(inst_array):
                return lambda eng, c, insts=inst_array: eng.execute_instructions(insts, c)
            
            card.effects.append(Effect(
                trigger_name, 
                make_instruction_action(instructions), 
                max_uses=current_max_uses
            ))
            
    return card


# ==========================================
# 3. Streamlit UI 构建 
# ==========================================
st.set_page_config(page_title="WS专业斩杀演算", layout="wide")
st.markdown("""
    <style>
    .stButton > button { border-color: #ff4b4b; color: #ff4b4b; float: right; }
    .stButton > button:hover { background-color: #ff4b4b; color: white; }
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🗡️ Weiss Schwarz 终盘斩杀演算 (专业赛级)")

cfg = {}

with st.sidebar:
    st.header("⚙️ 全局设置")
    # 🌟 新增：UI 开关，默认开启
    cfg["p_force_trigger"] = st.checkbox("🔥 开启上帝模式 (忽略效果发动条件)", True)

    st.divider()
    st.header("🎯 对方（防守方）状态")
    cfg["o_advanced"] = st.checkbox("🔮 开启精确录入已知公开区域 (算牌)", False, key="o_adv")
    
    if cfg["o_advanced"]:
        st.info("已开启精确算牌模式，系统将严格使用下方填写的真实数据！")
        cfg["o_lvl_adv"] = st.number_input("精确 - 当前等级", 0, 3, 3, key="oa_lvl")
        
        st.subheader("卡组 (Deck)")
        cfg["o_dk_total"] = st.number_input("卡组总张数", 0, 50, 30, key="oa_dk_t")
        col1, col2 = st.columns(2)
        cfg["o_dk_cx1"] = col1.number_input("第一种CX张数", 0, 4, 0, key="oa_dk_cx1")
        cfg["o_dk_cx1_type"] = col1.selectbox("类型", CX_OPTIONS, index=8, key="oa_dk_cx1_t")
        cfg["o_dk_cx2"] = col2.number_input("第二种CX张数", 0, 4, 0, key="oa_dk_cx2")
        cfg["o_dk_cx2_type"] = col2.selectbox("类型", CX_OPTIONS, index=0, key="oa_dk_cx2_t")
        
        st.subheader("控室 (Waiting Room)")
        cfg["o_wr_total"] = st.number_input("控室总张数", 0, 50, 30, key="oa_wr_t")
        cfg["o_wr_l3"] = st.number_input("3级 张数 (默认带Trigger)", 0, 50, 8, key="oa_wr_3")
        cfg["o_wr_l2"] = st.number_input("2级 张数 (默认带Trigger)", 0, 50, 2, key="oa_wr_2")
        cfg["o_wr_l1"] = st.number_input("1级 张数 (无Trigger)", 0, 50, 10, key="oa_wr_1")
        cfg["o_wr_l0"] = st.number_input("0级 张数 (无Trigger)", 0, 50, 4, key="oa_wr_0")
        cfg["o_wr_l2e"] = st.number_input("2级事件 张数", 0, 50, 0, key="oa_wr_2e")
        col3, col4 = st.columns(2)
        cfg["o_wr_cx1"] = col3.number_input("第一种CX", 0, 4, 0, key="oa_wr_cx1")
        cfg["o_wr_cx1_type"] = col3.selectbox("类型", CX_OPTIONS, index=8, key="oa_wr_cx1_t")
        cfg["o_wr_cx2"] = col4.number_input("第二种CX", 0, 4, 0, key="oa_wr_cx2")
        cfg["o_wr_cx2_type"] = col4.selectbox("类型", CX_OPTIONS, index=0, key="oa_wr_cx2_t")

        st.subheader("时计区 (Clock)")
        cfg["o_clk_l3"] = st.number_input("Clock 3级", 0, 50, 0, key="oa_c_3")
        cfg["o_clk_l2"] = st.number_input("Clock 2级", 0, 50, 2, key="oa_c_2")
        cfg["o_clk_l1"] = st.number_input("Clock 1级", 0, 50, 0, key="oa_c_1")
        cfg["o_clk_l0"] = st.number_input("Clock 0级", 0, 50, 0, key="oa_c_0")
        cfg["o_clk_l2e"] = st.number_input("Clock 2级事件", 0, 50, 0, key="oa_c_2e")
        col5, col6 = st.columns(2)
        cfg["o_clk_cx1"] = col5.number_input("Clock 第一种CX", 0, 4, 0, key="oa_c_cx1")
        cfg["o_clk_cx1_type"] = col5.selectbox("类型", CX_OPTIONS, index=8, key="oa_c_cx1_t")
        cfg["o_clk_cx2"] = col6.number_input("Clock 第二种CX", 0, 4, 0, key="oa_c_cx2")
        cfg["o_clk_cx2_type"] = col6.selectbox("类型", CX_OPTIONS, index=0, key="oa_c_cx2_t")
        
        st.caption("提示：血区中的卡会在升级时根据 WS 规则自动回到控室。")
        
    else:
        cfg["o_lvl"] = st.number_input("当前等级", 0, 3, 3, key="ob_lvl")
        cfg["o_clk"] = st.number_input("当前时计总数", 0, 6, 0, key="ob_clk")
        cfg["o_deck"] = st.number_input("卡组总张数", 0, 50, 30, key="ob_dk")
        cfg["o_cx"] = st.number_input("卡组剩余 CX (张)", 0, 8, 8, key="ob_cx")

    st.write("--- 共享资源 ---")
    cfg["o_stock"] = st.number_input("Stock 张数", 0, 50, 0, key="o_stk")
    cfg["o_hand"] = st.number_input("手牌 张数", 0, 50, 0, key="o_hnd")
    cfg["o_memory"] = st.number_input("Memory 张数", 0, 50, 0, key="o_mem")
    st.write("对面场上角色数量：")
    cfg["o_front"] = st.number_input("前排角色", 0, 3, 3, key="o_frt")
    cfg["o_back"] = st.number_input("后排角色", 0, 2, 2, key="o_bak")

    st.divider()
    
    st.header("🔥 自己（攻击方）状态")
    cfg["p_advanced"] = st.checkbox("🔮 开启精确录入已知公开区域 (算牌)", False, key="p_adv")
    
    if cfg["p_advanced"]:
        st.info("已开启精确算牌模式，系统将严格使用下方填写的真实数据！")
        st.subheader("卡组 (Deck)")
        cfg["p_dk_total"] = st.number_input("卡组总张数", 0, 50, 30, key="pa_dk_t")
        cfg["p_dk_cx_tot"] = st.number_input("卡组CX总计", 0, 8, 8, key="pa_dk_cxtot")
        cfg["p_dk_l3"] = st.number_input("卡组 3级", 0, 50, 8, key="pa_dk_3")
        cfg["p_dk_l2"] = st.number_input("卡组 2级", 0, 50, 2, key="pa_dk_2")
        cfg["p_dk_l1"] = st.number_input("卡组 1级", 0, 50, 10, key="pa_dk_1")
        cfg["p_dk_l0"] = st.number_input("卡组 0级", 0, 50, 4, key="pa_dk_0")
        cfg["p_dk_l2e"] = st.number_input("卡组 2级事件", 0, 50, 0, key="pa_dk_2e")
        c7, c8 = st.columns(2)
        cfg["p_dk_cx1"] = c7.number_input("卡组 第一种CX", 0, 4, 4, key="pa_dk_cx1_adv")
        cfg["p_dk_cx1_type"] = c7.selectbox("类型", CX_OPTIONS, index=8, key="pa_dk_cx1_t_adv")
        cfg["p_dk_cx2"] = c8.number_input("卡组 第二种CX", 0, 4, 4, key="pa_dk_cx2_adv")
        cfg["p_dk_cx2_type"] = c8.selectbox("类型", CX_OPTIONS, index=0, key="pa_dk_cx2_t_adv")
        
        st.subheader("控室 (Waiting Room)")
        cfg["p_wr_total"] = st.number_input("控室总张数", 0, 50, 30, key="pa_wr_t")
        cfg["p_wr_l3"] = st.number_input("WR 3级", 0, 50, 8, key="pa_wr_3")
        cfg["p_wr_l2"] = st.number_input("WR 2级", 0, 50, 2, key="pa_wr_2")
        cfg["p_wr_l1"] = st.number_input("WR 1级", 0, 50, 10, key="pa_wr_1")
        cfg["p_wr_l0"] = st.number_input("WR 0级", 0, 50, 4, key="pa_wr_0")
        cfg["p_wr_l2e"] = st.number_input("WR 2级事件", 0, 50, 0, key="pa_wr_2e")
        c9, c10 = st.columns(2)
        cfg["p_wr_cx1"] = c9.number_input("WR 第一种CX", 0, 4, 0, key="pa_wr_cx1")
        cfg["p_wr_cx1_type"] = c9.selectbox("类型", CX_OPTIONS, index=8, key="pa_wr_cx1_t")
        cfg["p_wr_cx2"] = c10.number_input("WR 第二种CX", 0, 4, 0, key="pa_wr_cx2")
        cfg["p_wr_cx2_type"] = c10.selectbox("类型", CX_OPTIONS, index=0, key="pa_wr_cx2_t")

        st.subheader("时计区 (Clock)")
        cfg["p_clk_l3"] = st.number_input("Clock 3级", 0, 50, 0, key="pa_c_3")
        cfg["p_clk_l2"] = st.number_input("Clock 2级", 0, 50, 2, key="pa_c_2")
        cfg["p_clk_l1"] = st.number_input("Clock 1级", 0, 50, 0, key="pa_c_1")
        cfg["p_clk_l0"] = st.number_input("Clock 0级", 0, 50, 0, key="pa_c_0")
        cfg["p_clk_l2e"] = st.number_input("Clock 2级事件", 0, 50, 0, key="pa_c_2e")
        c13, c14 = st.columns(2)
        cfg["p_clk_cx1"] = c13.number_input("Clock 第一种CX", 0, 4, 0, key="pa_c_cx1")
        cfg["p_clk_cx1_type"] = c13.selectbox("类型", CX_OPTIONS, index=8, key="pa_c_cx1_t")
        cfg["p_clk_cx2"] = c14.number_input("Clock 第二种CX", 0, 4, 0, key="pa_c_cx2")
        cfg["p_clk_cx2_type"] = c14.selectbox("类型", CX_OPTIONS, index=0, key="pa_c_cx2_t")

    else:
        cfg["p_deck"] = st.number_input("卡组总张数", 0, 50, 30, key="p_dk")
        cfg["p_trig"] = st.number_input("卡组 基础魂标张数", 0, 50, 6, key="p_trg")
        c11, c12 = st.columns(2)
        cfg["p_dk_cx1"] = c11.number_input("第一种CX张数", 0, 4, 4, key="p_dk_cx1")
        cfg["p_dk_cx1_type"] = c11.selectbox("类型", CX_OPTIONS, index=8, key="p_dk_cx1_t")
        cfg["p_dk_cx2"] = c12.number_input("第二种CX张数", 0, 4, 4, key="p_dk_cx2")
        cfg["p_dk_cx2_type"] = c12.selectbox("类型", CX_OPTIONS, index=0, key="p_dk_cx2_t")

    st.write("--- 共享资源 ---")
    cfg["p_stock"] = st.number_input("己方 Stock 张数", 0, 50, 0, key="p_stk")
    cfg["p_hand"] = st.number_input("己方 手牌 张数", 0, 50, 0, key="p_hnd")
    cfg["p_memory"] = st.number_input("己方 Memory 张数", 0, 50, 0, key="p_mem")

def reset_slot(suffix, def_val):
    st.session_state[f"sel_{suffix}"] = "无 (Empty)"
    st.session_state[f"val_{suffix}"] = def_val

def render_slot(col, label, suffix, is_event=False, def_val=2):
    sel_key = f"sel_{suffix}"
    val_key = f"val_{suffix}"
    if sel_key not in st.session_state: st.session_state[sel_key] = "无 (Empty)"
    if val_key not in st.session_state: st.session_state[val_key] = def_val

    user_choices = {}
    with col:
        h_l, h_r = st.columns([3, 1])
        h_l.write(f"**{label}**")
        h_r.button("×", key=f"btn_{suffix}", on_click=reset_slot, args=(suffix, def_val))
        sel = st.selectbox("卡牌", CARD_OPTIONS, key=sel_key, label_visibility="collapsed")
        v_lbl = "效果/事件发动次数" if is_event else "攻击基础魂点"
        st.caption(v_lbl)
        val = st.number_input(v_lbl, 0, 10, key=val_key, label_visibility="collapsed")
        
        if sel != "无 (Empty)":
            card_data = RAW_DB[sel]
            img = card_data.get("image")
            if img: st.image(img, use_container_width=True)
            
            # 🌟 动态渲染下拉战术菜单！(如果你在 JSON 里配了原版文字，这里就会显示原版文字)
            for i, eff in enumerate(card_data.get("effects", [])):
                if eff.get("is_choice"):
                    options = [c.get("label", f"效果选项 {j+1}") for j, c in enumerate(eff.get("choices", []))]
                    choice_label = st.selectbox(f"⚙️ {eff.get('trigger')} 发动战术", options, key=f"choice_{suffix}_{i}")
                    user_choices[i] = options.index(choice_label)
        else: 
            st.info("空槽位")
            
    return sel, val, user_choices

st.subheader("⚔️ 前排攻击 Stage")
f1, f2, f3 = st.columns(3)
p1_name, p1_val, p1_choices = render_slot(f1, "左列", "p1", def_val=2)
p2_name, p2_val, p2_choices = render_slot(f2, "中列", "p2", def_val=2)
p3_name, p3_val, p3_choices = render_slot(f3, "右列", "p3", def_val=2)

st.divider()
st.subheader("⛺ 后排支援 & 事件")
b1, b2, ev = st.columns(3)
s1_name, s1_val, s1_choices = render_slot(b1, "左后支援", "b1", def_val=0)
s2_name, s2_val, s2_choices = render_slot(b2, "右后支援", "b2", def_val=0)
e1_name, e1_val, e1_choices = render_slot(ev, "⭐ 特殊事件/效果栏", "e1", is_event=True, def_val=1)

st.divider()
iters = st.number_input("模拟演算次数", min_value=1, max_value=100000, value=1, step=1)

if st.button("🚀 开始斩杀演算", use_container_width=True):
    with st.spinner("蒙特卡洛引擎高速运算中..."):
        kills = 0
        reach_3_6 = 0
        
        for i in range(iters):
            if iters == 1:
                print(f"\n========== 🚀 开始第 {i+1} 次模拟局 ==========")
                
            engine = GameEngine(cfg)
            
            attackers = []
            supports = []
            
            # 🌟 传入选择好的下拉框战术 (user_choices)
            for name, val, choices in [(p1_name, p1_val, p1_choices), (p2_name, p2_val, p2_choices), (p3_name, p3_val, p3_choices)]:
                if name != "无 (Empty)":
                    card_obj = create_card_instance(name, val, max_uses=99, user_choices=choices)
                    if card_obj: attackers.append(card_obj)
            
            for idx, (name, val, choices) in enumerate([(s1_name, s1_val, s1_choices), (s2_name, s2_val, s2_choices), (e1_name, e1_val, e1_choices)]):
                if name != "无 (Empty)":
                    max_u = val if idx == 2 else 99 
                    card_obj = create_card_instance(name, 0, max_uses=max_u, user_choices=choices)
                    if card_obj: supports.append(card_obj)
            
            engine.all_active_cards.extend(attackers + supports)
            
            for idx, attacker in enumerate(attackers):
                if iters == 1:
                    print(f"\n--- ⚔️ 第 {idx+1} 个槽位攻击者 [{attacker.name}] 开始攻击 ---")
                engine.simulate_attack(attacker)
                if engine.opp_level >= 4: 
                    if iters == 1:
                        print("💀 对手已阵亡，停止本局后续攻击")
                    break
            
            if engine.opp_level >= 4: kills += 1
            if (engine.opp_level == 3 and len(engine.opp_clock_zone) == 6) or engine.opp_level >= 4: reach_3_6 += 1
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("最终斩杀成功率 (3-7+)", f"{(kills/iters)*100:.2f}%")
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("打到 3-6 的概率", f"{(reach_3_6/iters)*100:.2f}%")
            st.markdown('</div>', unsafe_allow_html=True)
