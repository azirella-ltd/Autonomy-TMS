# Sprint 5 Quick Start Guide

**Goal**: Implement gamification, reporting, templates, onboarding, and performance improvements

---

## 🎯 Sprint 5 at a Glance

| Feature | Time | Priority | Complexity |
|---------|------|----------|------------|
| 1. Gamification System | 2-3 days | HIGH | MEDIUM |
| 2. Advanced Reporting | 1-2 days | HIGH | LOW |
| 3. Game Templates | 1-2 days | MEDIUM | LOW |
| 4. Onboarding & Help | 1 day | MEDIUM | LOW |
| 5. Performance Optimization | 1 day | HIGH | MEDIUM |

**Total**: 5-7 days

---

## 🚀 Quick Implementation Path

### Option A: Full Sprint (Recommended)
Implement all 5 features sequentially

**Timeline**: 5-7 days
**Outcome**: Polished, production-ready platform

### Option B: MVP Sprint (Fast Path)
Implement core gamification + reporting only

**Timeline**: 3-4 days
**Features**: Achievements, leaderboards, game reports
**Outcome**: Enhanced engagement with minimal time

### Option C: Polish-Only Sprint (Lightest)
Skip new features, focus on performance + onboarding

**Timeline**: 2-3 days
**Features**: Tutorial, help system, optimizations
**Outcome**: Better UX, faster performance

---

## 📋 Implementation Checklist

### Day 1: Gamification Backend
- [ ] Create database migration (achievements, player_stats)
- [ ] Implement GamificationService
- [ ] Create API endpoints
- [ ] Seed default achievements
- [ ] Test achievement unlocking logic

**Files to Create**:
```
backend/app/models/achievement.py
backend/app/services/gamification_service.py
backend/app/api/endpoints/gamification.py
backend/migrations/sprint5_gamification.sql
```

**Quick Test**:
```bash
# Run migration
docker compose exec -T db mysql -u beer_user -p'change-me-user' beer_game < backend/migrations/sprint5_gamification.sql

# Test API
curl http://localhost:8000/api/v1/gamification/players/1/achievements
```

---

### Day 2: Gamification Frontend
- [ ] Create AchievementsPanel component
- [ ] Create LeaderboardPanel component
- [ ] Add player profile badge to UI
- [ ] Add achievement notifications (toasts)
- [ ] Test in browser

**Files to Create**:
```
frontend/src/components/game/AchievementsPanel.jsx
frontend/src/components/game/LeaderboardPanel.jsx
frontend/src/services/gamificationApi.js
```

**Quick Test**:
- Navigate to Achievements tab
- Unlock an achievement
- Check leaderboard displays

---

### Day 3: Reporting & Analytics
- [ ] Implement ReportingService
- [ ] Add export functionality (CSV, JSON, Excel)
- [ ] Create ReportsPanel component
- [ ] Add trend charts
- [ ] Test exports

**Files to Create**:
```
backend/app/services/reporting_service.py
backend/app/api/endpoints/reporting.py
frontend/src/components/game/ReportsPanel.jsx
frontend/src/components/analytics/TrendChart.jsx
```

**Quick Test**:
- Generate game report
- Export to CSV
- View trends chart

---

### Day 4: Templates & Onboarding
- [ ] Implement TemplateService
- [ ] Create template database table
- [ ] Build TemplatesGallery component
- [ ] Add tutorial component (react-joyride)
- [ ] Create help center

**Files to Create**:
```
backend/app/models/game_template.py
backend/app/services/template_service.py
frontend/src/components/game/TemplatesGallery.jsx
frontend/src/components/onboarding/Tutorial.jsx
frontend/src/components/help/HelpCenter.jsx
```

**Quick Test**:
- Save game as template
- Create game from template
- Run tutorial for new user
- Search help articles

---

### Day 5: Performance & Polish
- [ ] Add database indexes
- [ ] Implement caching (Redis)
- [ ] Add rate limiting
- [ ] Optimize React components (memo, useMemo)
- [ ] Add code splitting
- [ ] Run load tests

**Files to Modify**:
```
backend/app/db/optimization.py
backend/app/api/middleware/caching.py
backend/app/api/middleware/rate_limiting.py
frontend/src/App.jsx (lazy loading)
frontend/src/components/* (memoization)
```

**Quick Test**:
```bash
# Load test with Apache Bench
ab -n 1000 -c 10 http://localhost:8000/api/health

# Check cache hit rate
redis-cli info stats | grep keyspace_hits
```

---

## 🔧 Setup Instructions

### Prerequisites
```bash
# Ensure Sprint 4 is complete
docker compose ps  # All services should be healthy

# Ensure database is accessible
docker compose exec -T db mysql -u beer_user -p'change-me-user' beer_game -e "SELECT 1"
```

### Install Dependencies

**Backend**:
```bash
cd backend
pip install redis slowapi openpyxl
```

**Frontend**:
```bash
cd frontend
npm install react-joyride react-window
```

### Start Development
```bash
# Backend hot reload (already running)
docker compose logs backend -f

# Frontend hot reload (already running)
docker compose logs frontend -f
```

---

## 🧪 Testing Strategy

### Unit Tests
```python
# backend/tests/test_gamification_service.py
def test_achievement_unlock():
    service = GamificationService(db)
    result = await service.check_achievements(player_id=1, game_id=1)
    assert result['newly_unlocked'] == ['First Steps']

def test_level_calculation():
    service = GamificationService(db)
    level = await service.calculate_player_level(total_points=100)
    assert level == 3  # floor(sqrt(100/10)) = 3
```

### Integration Tests
```python
# Test full achievement flow
1. Player completes game
2. Achievement check triggered
3. "First Steps" unlocks
4. Player stats updated
5. Notification sent
```

### Browser Tests
```javascript
// Cypress test
describe('Gamification', () => {
  it('displays achievements', () => {
    cy.visit('/game/1')
    cy.get('[data-testid="achievements-tab"]').click()
    cy.contains('First Steps').should('be.visible')
  })

  it('shows leaderboard', () => {
    cy.visit('/leaderboard')
    cy.contains('Global').click()
    cy.get('table tbody tr').should('have.length.greaterThan', 0)
  })
})
```

---

## 📊 Success Metrics

### Track These KPIs

**Engagement**:
- Achievement unlock rate
- Leaderboard views
- Template usage
- Tutorial completion rate

**Performance**:
- API response time (p95 < 200ms)
- Page load time (< 2s)
- Database query time (< 50ms)
- Cache hit rate (> 80%)

**User Satisfaction**:
- Game completion rate
- Session duration
- Feature usage (analytics, negotiations)
- User feedback score

### Monitoring
```python
# Add to backend/app/core/metrics.py
from prometheus_client import Counter, Histogram

achievement_unlocks = Counter('achievement_unlocks_total', 'Total achievement unlocks')
api_request_duration = Histogram('api_request_duration_seconds', 'API request duration')

# In code
achievement_unlocks.inc()
api_request_duration.observe(response_time)
```

---

## 🐛 Common Issues & Solutions

### Issue: Achievements not unlocking
**Solution**: Check achievement criteria match player stats exactly
```python
# Debug
player_stats = await get_player_stats(player_id)
print(f"Player stats: {player_stats}")
print(f"Achievement criteria: {achievement.criteria}")
```

### Issue: Leaderboard not updating
**Solution**: Ensure player_stats table triggers update
```sql
-- Add trigger
CREATE TRIGGER update_leaderboard_on_achievement
AFTER INSERT ON player_achievements
FOR EACH ROW
BEGIN
    UPDATE player_stats
    SET total_points = total_points + (
        SELECT points FROM achievements WHERE id = NEW.achievement_id
    )
    WHERE player_id = NEW.player_id;
END;
```

### Issue: Export fails for large games
**Solution**: Stream data instead of loading all at once
```python
async def export_game_streaming(game_id: int):
    def generate():
        for chunk in get_data_chunks(game_id):
            yield chunk
    return StreamingResponse(generate(), media_type='text/csv')
```

### Issue: Tutorial interfering with actual gameplay
**Solution**: Only show tutorial on first login
```javascript
const [showTutorial, setShowTutorial] = useState(() => {
  return !localStorage.getItem('tutorial_completed')
})

const completeTutorial = () => {
  localStorage.setItem('tutorial_completed', 'true')
  setShowTutorial(false)
}
```

---

## 📝 Code Snippets

### Quick Achievement Check
```python
# After player action
from app.services.gamification_service import check_achievements

@router.post("/games/{game_id}/rounds/{round_id}/complete")
async def complete_round(game_id: int, round_id: int, db: Session):
    # ... game logic ...

    # Check achievements for all players
    for player in game.players:
        await check_achievements(player.id, game_id, db)

    return {"status": "completed"}
```

### Quick Template Creation
```python
# Save current game as template
@router.post("/games/{game_id}/save-as-template")
async def save_as_template(
    game_id: int,
    template: TemplateCreate,
    db: Session,
    current_user: User = Depends(get_current_user)
):
    game = await get_game(game_id, db)

    new_template = GameTemplate(
        name=template.name,
        description=template.description,
        config_id=game.config_id,
        settings={
            "num_rounds": game.num_rounds,
            "holding_cost": game.holding_cost,
            "backlog_cost": game.backlog_cost
        },
        created_by=current_user.id
    )

    db.add(new_template)
    await db.commit()
    return new_template
```

### Quick Report Export
```python
import pandas as pd
from fastapi.responses import StreamingResponse
from io import BytesIO

@router.get("/reports/games/{game_id}/export")
async def export_game_report(game_id: int, format: str = 'csv'):
    # Get game data
    rounds = await get_game_rounds(game_id)

    # Create DataFrame
    df = pd.DataFrame(rounds)

    # Export based on format
    if format == 'csv':
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type='text/csv',
            headers={'Content-Disposition': f'attachment; filename=game_{game_id}.csv'}
        )
    elif format == 'excel':
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename=game_{game_id}.xlsx'}
        )
```

---

## 🎓 Learning Resources

### Gamification Best Practices
- [Octalysis Framework](https://yukaichou.com/gamification-examples/octalysis-complete-gamification-framework/)
- [Achievement Design Patterns](https://www.gamasutra.com/view/feature/134842/the_achievement_design.php)

### React Performance
- [React Optimization Guide](https://react.dev/learn/render-and-commit)
- [useMemo and useCallback](https://react.dev/reference/react/useMemo)

### Database Optimization
- [MySQL Index Guide](https://dev.mysql.com/doc/refman/8.0/en/mysql-indexes.html)
- [Query Optimization](https://dev.mysql.com/doc/refman/8.0/en/optimization.html)

---

## 🎯 Decision Tree

**Should I implement Sprint 5?**

```
Are you happy with Sprint 4 features?
├─ No → Test and fix Sprint 4 first
└─ Yes → Do you want more engagement?
    ├─ No → Skip to Sprint 6 (Enterprise features)
    └─ Yes → Do you have 5-7 days?
        ├─ No → Implement MVP Sprint (3-4 days)
        └─ Yes → Implement Full Sprint 5 ✅
```

---

## 📞 Next Steps

1. **Review Sprint 5 Plan**: Read PHASE7_SPRINT5_PLAN.md
2. **Choose Implementation Path**: Full/MVP/Polish-only
3. **Set Timeline**: Block 5-7 days on calendar
4. **Start Day 1**: Gamification backend
5. **Track Progress**: Update SPRINT5_PROGRESS.md daily

---

**Ready to Start?** Open PHASE7_SPRINT5_PLAN.md for detailed specifications!

**Questions?** Review the plan or ask for clarification on specific features.

**Want Something Different?** Let me know what features are most important to you!
