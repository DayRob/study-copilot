from dataclasses import dataclass, replace

TIER_ORDER = ["easy", "medium", "hard"]

XP_BASE = {"easy": 10, "medium": 20, "hard": 35}
STREAK_BONUS_PER_STEP = 0.03
STREAK_BONUS_CAP = 1.3
STREAK_CAP_FOR_BONUS = 10

TIER_UP_EVERY = 3       # consecutive correct answers to step up a tier
TIER_DOWN_AFTER = 2     # consecutive wrong answers to step down a tier
STARTING_LIVES = 3

LEVEL_XP_UNIT = 150     # triangular growth unit for the persistent level curve
MAX_DISPLAYED_LEVEL = 15


def step_tier(tier: str, delta: int) -> str:
    idx = TIER_ORDER.index(tier)
    idx = max(0, min(len(TIER_ORDER) - 1, idx + delta))
    return TIER_ORDER[idx]


def xp_for_answer(difficulty: str, streak_before_answer: int) -> int:
    base = XP_BASE.get(difficulty, XP_BASE["easy"])
    multiplier = min(1 + min(streak_before_answer, STREAK_CAP_FOR_BONUS) * STREAK_BONUS_PER_STEP, STREAK_BONUS_CAP)
    return round(base * multiplier)


def xp_required_for_level(level: int) -> int:
    """Cumulative XP needed to reach `level` (level 1 = 0 XP, triangular growth)."""
    if level <= 1:
        return 0
    n = level - 1
    return LEVEL_XP_UNIT * n * (n + 1) // 2


def level_from_xp(xp: int, max_level: int = MAX_DISPLAYED_LEVEL) -> int:
    level = 1
    while level < max_level and xp >= xp_required_for_level(level + 1):
        level += 1
    return level


def starting_tier_for_level(level: int) -> str:
    if level <= 2:
        return "easy"
    if level <= 5:
        return "medium"
    return "hard"


@dataclass
class SessionState:
    difficulty_tier: str
    current_streak: int
    wrong_streak: int
    lives_remaining: int
    score: int
    xp_earned: int
    questions_answered: int
    questions_correct: int
    best_streak: int


@dataclass
class AnswerResult:
    state: SessionState
    xp_awarded: int
    tier_changed: bool
    game_over: bool


def apply_answer(state: SessionState, is_correct: bool, question_difficulty: str) -> AnswerResult:
    """Pure state transition for one answered question. No DB/IO here so the
    tier/streak/XP rules can be unit-tested in isolation from the API layer."""
    new_state = replace(state)
    new_state.questions_answered += 1
    tier_changed = False
    xp_awarded = 0

    if is_correct:
        xp_awarded = xp_for_answer(question_difficulty, new_state.current_streak)
        new_state.current_streak += 1
        new_state.wrong_streak = 0
        new_state.score += 10
        new_state.xp_earned += xp_awarded
        new_state.questions_correct += 1
        new_state.best_streak = max(new_state.best_streak, new_state.current_streak)
        if new_state.current_streak % TIER_UP_EVERY == 0:
            stepped = step_tier(new_state.difficulty_tier, 1)
            tier_changed = stepped != new_state.difficulty_tier
            new_state.difficulty_tier = stepped
    else:
        new_state.current_streak = 0
        new_state.wrong_streak += 1
        if new_state.wrong_streak >= TIER_DOWN_AFTER:
            # The tier-down IS this mistake's consequence -- don't also burn a
            # life on the same answer. Without this, 2 wrong answers in a row
            # cost 2 of 3 starting lives *and* drop a tier, leaving almost no
            # room to benefit from the easier tier before a 3rd miss ends the
            # game -- the exact "double punishment" this mechanic exists to avoid.
            stepped = step_tier(new_state.difficulty_tier, -1)
            tier_changed = stepped != new_state.difficulty_tier
            new_state.difficulty_tier = stepped
            new_state.wrong_streak = 0
        else:
            new_state.lives_remaining = max(0, new_state.lives_remaining - 1)

    game_over = new_state.lives_remaining <= 0
    return AnswerResult(state=new_state, xp_awarded=xp_awarded, tier_changed=tier_changed, game_over=game_over)
