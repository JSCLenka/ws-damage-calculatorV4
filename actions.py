import random

# ==========================================
# WS 核心斩杀 Action 映射表 (独立模块)
# ==========================================
# 所有的 Action 函数都严格接收三个参数：
# eng: GameEngine 实例 (你的游戏物理引擎，用于调用各种基础规则)
# src: Card 实例 (触发该效果的源卡牌)
# amt: int (效果相关的数值，如烧血量、推牌量)

ACTION_MAP = {
    # ==================================================
    # 🟢 原始基础 Action (常规斩杀机制)
    # ==================================================
    
    # 1. 标准烧血 (可被取消)
    "Burn": lambda eng, src, amt: eng.deal_damage(amt),
    
    # 2. 武藏烧 (看顶等级+1)
    "Musashi": lambda eng, src, _: eng.deal_damage(eng.get_opp_top_level() + 1),
    
    # 3. 传火 (通常挂在 OnDamageCancel 触发器上)
    "PassTheTorch": lambda eng, src, amt: eng.deal_damage(amt),
    
    # 4. 推底烧 (推底 X 枚，根据 CX 数烧)
    "BottomMillBurn": lambda eng, src, amt: eng.deal_damage(eng.mill_opp(amt, from_top=False)),
    
    # 5. 傲慢加特林 (魂点拆分成 X 次 1 伤)
    "SplitAttack": lambda eng, src, _: [eng.deal_damage(1) for _ in range(getattr(src, 'soul', 1))],
    
    # 6. 强制进血 (无法被取消)
    "ForcedClockBurn": lambda eng, src, amt: eng.take_damage(amt),
    
    # 7. 判魂烧 (RaDragon: 判定有魂标则烧 X)
    "RaDragon": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_player_top("soul") else None,
    
    # 8. 摩卡 (Moca: 封印牌顶 CX)
    "Moca": lambda eng, src, amt: eng.moca_effect(amt),
    
    # 9. 再动 (Restand)
    "Restand": lambda eng, src, _: eng.simulate_attack(src),
    
    # 10. 封顶 (打倒时将对手角色放回牌顶 - 模拟为下次攻击必中)
    "ReverseTopDeck": lambda eng, src, _: eng.opp_deck.insert(0, {"is_cx": False, "level": 0}),
    
    # 11. 踢人进血 (ClockKick)
    "ClockKick": lambda eng, src, _: eng.take_damage(1),
    
    # 12. 推顶烧 (推顶 X 枚，根据 CX 数烧)
    "OppTopMillBurn": lambda eng, src, amt: eng.deal_damage(eng.mill_opp(amt, from_top=True)),
    
    # 13. 查自顶烧 (自己顶是 L3 或魂标则烧 X)
    "PlayerTopCheckBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_player_top("level3") else None,

    # ==================================================
    # 🚨 AI 提取并扩充的 15 个高级 Action (牌库赌博与条件特化)
    # ==================================================
    
    # 14. 取消时烧血 (等同于 PassTheTorch 传火，为了迎合 AI 的命名习惯保留)
    "CancelBurn": lambda eng, src, amt: eng.deal_damage(amt, source_card=src),
    
    # 15. 满足条件烧血 (因为我们是 Happy Path 假设条件全满足，所以直接烧)
    "ConditionBurn": lambda eng, src, amt: eng.deal_damage(amt),

    # 16. 推底，如果是 CX 则烧血
    "BottomMillCxBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_bottom(condition="cx") else None,
    
    # 17. 推底，如果是 0 级则烧血 (黑川赤音效果)
    "BottomMillLevel0Burn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_bottom(condition="level_0") else None,
    
    # 18. 推底，如果是特定等级则烧血
    "BottomMillLevelBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_bottom(condition="level_match") else None,
    
    # 19. 看牌底，如果是 CX 则踢人进血 (ClockKick 无法取消，所以用 take_damage)
    "BottomCheckCxClockKick": lambda eng, src, amt: eng.take_damage(1) if eng.check_bottom(condition="cx") else None,

    # 20. 看对手牌顶，如果是 CX 则烧血
    "TopCheckCxBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_opp_top(condition="cx") else None,
    
    # 21. 看对手牌顶，如果是特定等级则烧血
    "TopCheckLevelBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_opp_top(condition="level_match") else None,
    
    # 22. 看对手牌顶，满足特定条件则烧血
    "TopCheckConditionBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_opp_top(condition="any") else None,
    
    # 23. 推对手牌顶到休息室，如果是 CX 则烧血
    "TopMillCxBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_opp_top(condition="cx") else None,
    
    # 24. 推对手牌顶到休息室，如果是特定等级则烧血
    "TopMillLevelBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_opp_top(condition="level_match") else None,

    # 25. 推对手牌顶到休息室，满足特定条件则烧血
    "TopMillConditionBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_opp_top(condition="any") else None,

     # #26 的变体：推自己牌顶，如果是 CX 则烧血 (amt)
    "PlayerTopMillCxBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_player_top(condition="cx") else None,
    
    # 新增：推自己牌顶，如果是魂标 (Soul) 则烧血 (amt)
    "PlayerTopMillSoulBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.mill_and_check_player_top(condition="soul") else None,
    
    # --- 复合动作 (小鲨鱼专用) ---
    # 逻辑：先 Burn 2，然后执行两次 [推顶判定魂标烧1]
    "GuraBurn": lambda eng, src, _: [
        eng.deal_damage(2),
        eng.deal_damage(1) if eng.mill_and_check_player_top(condition="soul") else None,
        eng.deal_damage(1) if eng.mill_and_check_player_top(condition="soul") else None
    ],
    
    # 27. 看自己牌顶，如果是特定等级则烧血
    "PlayerTopCheckLevelBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_player_top(condition="level_match") else None,
    
    # 28. 看自己牌顶，满足特定条件则烧血
    "PlayerTopCheckConditionBurn": lambda eng, src, amt: eng.deal_damage(amt) if eng.check_player_top(condition="any") else None,
}
