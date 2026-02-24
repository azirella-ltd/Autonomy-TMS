# Voice Signal Capture

Transcribe voice input and extract supply chain signals for the ForecastAdjustmentTRM.

## When to Use
- Planner dictates a market observation or customer intel
- Voice memo from field sales or logistics team
- Verbal override or forecast adjustment

## Process
1. Accept voice transcription (pre-processed by Whisper or equivalent)
2. Extract signal components: direction (up/down), magnitude hint, confidence
3. Classify signal type: DEMAND_SURGE, SUPPLY_DISRUPTION, COST_CHANGE, QUALITY_ISSUE
4. Submit via signal-capture skill

## API Flow
Use the `signal-capture` skill with extracted fields:
```
POST /api/v1/signals/ingest
{
  "source": "voice_memo",
  "signal_type": "<classified_type>",
  "direction": "up|down",
  "magnitude_hint": <number_or_null>,
  "site_id": "<site_key>",
  "signal_text": "<transcription_summary>",
  "signal_confidence": <0.0-1.0>,
  "channel": "openclaw_voice"
}
```

## Classification Rules
- Keywords "surge", "spike", "increase", "uptick" → direction: up
- Keywords "drop", "decline", "shortage", "disruption" → direction: down
- Percentages in text → magnitude_hint
- Confidence: 0.7 for clear statements, 0.4 for hedged/uncertain language
