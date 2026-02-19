# TRM Dashboard Enhancements

## Overview

Enhanced the TRM (Tiny Recursive Model) dashboard to support **config-specific training and progress tracking**. Each of the 7 supply chain configurations now requires separate TRM model training through all 5 curriculum phases.

## Supply Chain Configurations

The system supports 7 distinct supply chain configurations, each requiring its own trained TRM model:

1. **Default TBG** (`default_tbg`) - 4-node classic Beer Game
2. **Case TBG** (`case_tbg`) - Single manufacturer with 1:4 BOM
3. **Six-Pack TBG** (`six_pack_tbg`) - Two-level manufacturing
4. **Bottle TBG** (`bottle_tbg`) - Three-level manufacturing
5. **Three FG TBG** (`three_fg_tbg`) - Three finished goods
6. **Variable TBG** (`variable_tbg`) - Lognormal demand
7. **Complex SC** (`complex_sc`) - Multi-region complex network

## Training Requirements

- **Total Training Jobs**: 35 (7 configs × 5 phases)
- **Phases per Config**: 5 curriculum learning phases
- **Model Independence**: Each config requires a separate trained model

### Curriculum Learning Phases

1. **Phase 1**: Single-node base stock (simple inventory management)
2. **Phase 2**: 2-node supply chain (basic upstream/downstream)
3. **Phase 3**: 4-node Beer Game (classic configuration)
4. **Phase 4**: Multi-echelon variations (different topologies)
5. **Phase 5**: Production scenarios (manufacturing constraints)

## Frontend Changes

### TRMTrainingPanelEnhanced.jsx

Created new enhanced training panel (`/frontend/src/components/admin/TRMTrainingPanelEnhanced.jsx`) with:

**Key Features**:
- **Progress Matrix**: Visual table showing all 7 configs (rows) × 5 phases (columns)
- **Status Indicators**:
  - ✓ Checkmark for completed phases
  - ⏳ Pending icon for incomplete phases
  - Real-time progress updates during training
- **Overall Progress**: Percentage bar showing completion for each config
- **Click-to-Select**: Click any config row to select it for training
- **Config Dropdown**: Select specific configuration for training
- **Training Status**: Real-time monitoring with loss charts
- **Advanced Settings**: Accordion with all hyperparameters

**Component Structure**:
```javascript
const SUPPLY_CHAIN_CONFIGS = [
  { id: 'default_tbg', name: 'Default TBG', description: '...', phases: 5 },
  { id: 'case_tbg', name: 'Case TBG', description: '...', phases: 5 },
  // ... 7 configs total
];

// State management
const [selectedConfig, setSelectedConfig] = useState('default_tbg');
const [configProgress, setConfigProgress] = useState({});
const [trainingStatus, setTrainingStatus] = useState(null);
```

**Progress Loading**:
```javascript
const loadAllConfigProgress = async () => {
  const progress = {};
  for (const config of SUPPLY_CHAIN_CONFIGS) {
    const checkpoints = await trmApi.listCheckpoints('./checkpoints', config.id);
    // Calculate phase completion and overall progress
    progress[config.id] = {
      phases: {1: false, 2: false, 3: false, 4: false, 5: false},
      overall: 0
    };
  }
  setConfigProgress(progress);
};
```

### TRMDashboard.jsx

Updated to use enhanced panel:
```javascript
// Changed from:
import TRMTrainingPanel from '../../components/admin/TRMTrainingPanel';

// To:
import TRMTrainingPanel from '../../components/admin/TRMTrainingPanelEnhanced';
```

### trmApi.js

Enhanced API client to support config filtering:

```javascript
/**
 * List available checkpoints
 * @param {string} checkpointDir - Checkpoint directory
 * @param {string} configId - Optional supply chain config ID to filter by
 * @returns {Promise} List of checkpoints
 */
export const listCheckpoints = async (checkpointDir = './checkpoints', configId = null) => {
  const params = { checkpoint_dir: checkpointDir };
  if (configId) {
    params.config_id = configId;
  }
  const response = await api.get('/trm/checkpoints', { params });
  return response.data;
};
```

## Backend Changes

### TRM API Endpoint (/backend/app/api/endpoints/trm.py)

#### 1. Enhanced Checkpoint Listing

Updated `/trm/checkpoints` endpoint to support config-specific filtering:

```python
@router.get("/checkpoints")
async def list_checkpoints(
    checkpoint_dir: str = "./checkpoints",
    config_id: Optional[str] = None
):
    """
    List available TRM checkpoints.

    Args:
        checkpoint_dir: Directory containing checkpoints
        config_id: Optional supply chain config ID to filter by (e.g., 'default_tbg')
    """
    checkpoint_path = Path(checkpoint_dir)

    if not checkpoint_path.exists():
        return {"checkpoints": []}

    # Filter by config_id if provided
    pattern = f"{config_id}_*.pt" if config_id else "*.pt"

    checkpoints = []
    for file in checkpoint_path.glob(pattern):
        stat = file.stat()

        # Parse checkpoint metadata from filename
        # Expected format: {config_id}_phase{N}_epoch{M}.pt
        checkpoint_info = {
            "name": file.name,
            "path": str(file),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": stat.st_mtime,
            "phase": None,      # Parsed from filename
            "epoch": None,      # Parsed from filename
            "config_id": None   # Parsed from filename
        }

        # Parse phase, epoch, and config from filename
        filename = file.stem
        if "_phase" in filename and "_epoch" in filename:
            parts = filename.split("_")
            # Extract phase number
            # Extract epoch number
            # Extract config_id

        checkpoints.append(checkpoint_info)

    return {"checkpoints": checkpoints}
```

#### 2. Added Config Parameter to Training

Updated `TRMTrainingRequest` model:

```python
class TRMTrainingRequest(BaseModel):
    """Request to start TRM training."""
    supply_chain_config: str = Field("default_tbg", description="Supply chain config ID to train on")
    phase: str = Field(..., description="Training phase: 1-5 or 'all'")
    epochs: int = Field(50, description="Epochs per phase", ge=1, le=500)
    # ... other parameters
```

Updated training command to include config:

```python
cmd = [
    "python",
    str(script_path),
    "--supply-chain-config", request.supply_chain_config,  # NEW
    "--phase", str(request.phase),
    # ... other parameters
]
```

## Checkpoint Naming Convention

Checkpoints are now named with config-specific prefixes:

### New Format
```
{config_id}_phase{N}_epoch{M}.pt
```

**Examples**:
- `default_tbg_phase1_epoch10.pt`
- `case_tbg_phase2_epoch20.pt`
- `six_pack_tbg_phase3_epoch30.pt`
- `bottle_tbg_phase4_epoch40.pt`
- `three_fg_tbg_phase5_epoch50.pt`
- `variable_tbg_phase1_epoch15.pt`
- `complex_sc_phase2_epoch25.pt`

### Legacy Format (Backward Compatible)
```
trm_phase{N}_epoch{M}.pt
```

The API automatically parses both formats and marks legacy checkpoints with `config_id: "legacy"`.

## UI Workflow

### 1. View Progress Matrix

Upon loading the TRM dashboard training tab, users see:

```
┌──────────────────┬─────────┬─────────┬─────────┬─────────┬─────────┬──────────┐
│ Configuration    │ Phase 1 │ Phase 2 │ Phase 3 │ Phase 4 │ Phase 5 │ Progress │
├──────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──────────┤
│ Default TBG      │    ✓    │    ✓    │    ⏳   │    ⏳   │    ⏳   │   40%    │
│ Case TBG         │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    0%    │
│ Six-Pack TBG     │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    0%    │
│ Bottle TBG       │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    0%    │
│ Three FG TBG     │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    0%    │
│ Variable TBG     │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    0%    │
│ Complex SC       │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    ⏳   │    0%    │
└──────────────────┴─────────┴─────────┴─────────┴─────────┴─────────┴──────────┘
```

### 2. Select Configuration

Click on a row or use the configuration dropdown to select which config to train.

### 3. Configure Training

- **Select Phase**: Choose specific phase (1-5) or "All Phases" for curriculum learning
- **Set Hyperparameters**: Epochs, batch size, learning rate, model architecture
- **Choose Device**: CPU or CUDA (GPU)

### 4. Start Training

Click "Start Training" button. The system:
1. Validates parameters and device availability
2. Starts training in background
3. Updates status in real-time
4. Saves checkpoints with config-specific naming

### 5. Monitor Progress

During training:
- Real-time status updates every 3 seconds
- Progress bar showing epoch completion
- Live loss metrics (train loss, validation loss)
- Loss history chart

### 6. Resume Training

- View completed phases with checkmarks
- Select next incomplete phase
- Or select specific phase to retrain
- System automatically resumes from last checkpoint if available

## API Routes

### GET /api/v1/trm/checkpoints

**Query Parameters**:
- `checkpoint_dir` (optional): Checkpoint directory path (default: `./checkpoints`)
- `config_id` (optional): Filter by supply chain config ID (e.g., `default_tbg`)

**Response**:
```json
{
  "checkpoints": [
    {
      "name": "default_tbg_phase1_epoch20.pt",
      "path": "./checkpoints/default_tbg_phase1_epoch20.pt",
      "size_mb": 28.5,
      "modified": 1705456789.0,
      "phase": 1,
      "epoch": 20,
      "config_id": "default_tbg"
    }
  ]
}
```

### POST /api/v1/trm/train

**Request Body**:
```json
{
  "supply_chain_config": "default_tbg",
  "phase": "1",
  "epochs": 50,
  "device": "cuda",
  "batch_size": 32,
  "learning_rate": 0.0001,
  "num_samples": 10000,
  "d_model": 512,
  "nhead": 8,
  "num_layers": 2,
  "refinement_steps": 3,
  "checkpoint_dir": "./checkpoints",
  "resume_checkpoint": null
}
```

### GET /api/v1/trm/training-status

**Response**:
```json
{
  "status": "training",
  "phase": 1,
  "epoch": 15,
  "total_epochs": 50,
  "train_loss": 0.0234,
  "val_loss": 0.0256,
  "message": "Training in progress..."
}
```

## Training Workflow Example

### Training Default TBG (All Phases)

```bash
# UI: Select "Default TBG" from dropdown
# UI: Select "All Phases (Curriculum)" from phase dropdown
# UI: Click "Start Training"

# Backend executes:
python scripts/training/train_trm.py \
  --supply-chain-config default_tbg \
  --phase all \
  --epochs 50 \
  --device cuda \
  --batch-size 32 \
  --learning-rate 0.0001

# Checkpoints saved:
# ./checkpoints/default_tbg_phase1_epoch50.pt
# ./checkpoints/default_tbg_phase2_epoch50.pt
# ./checkpoints/default_tbg_phase3_epoch50.pt
# ./checkpoints/default_tbg_phase4_epoch50.pt
# ./checkpoints/default_tbg_phase5_epoch50.pt
```

### Training Specific Config and Phase

```bash
# UI: Select "Case TBG" from dropdown
# UI: Select "Phase 2: 2-node supply chain" from phase dropdown
# UI: Click "Start Training"

# Backend executes:
python scripts/training/train_trm.py \
  --supply-chain-config case_tbg \
  --phase 2 \
  --epochs 50 \
  --device cuda

# Checkpoint saved:
# ./checkpoints/case_tbg_phase2_epoch50.pt
```

## Benefits of Config-Specific Training

### 1. Specialized Models
Each supply chain configuration has unique characteristics:
- **Default TBG**: Simple 4-node linear chain
- **Case/Six-Pack/Bottle TBG**: Manufacturing with BOMs
- **Three FG TBG**: Multiple finished goods
- **Variable TBG**: Stochastic demand patterns
- **Complex SC**: Multi-region network topology

Training separate models allows each to specialize in its specific topology and dynamics.

### 2. Clear Progress Tracking
The progress matrix makes it immediately clear:
- Which configs have been trained
- Which phases are complete for each config
- Overall training coverage across all configs

### 3. Flexible Training Strategy
Users can:
- Train all phases for one config (vertical strategy)
- Train one phase across all configs (horizontal strategy)
- Train critical configs first (priority-based strategy)
- Resume interrupted training for specific configs

### 4. Independent Experimentation
Different configs can use different hyperparameters:
- More complex configs (Complex SC) might need more epochs
- Simpler configs (Default TBG) might train faster
- Manufacturing configs might need different model architectures

## Future Enhancements

### 1. Parallel Training
Enable training multiple configs simultaneously using GPU queuing:
```javascript
// UI: Multi-select configs and click "Train All Selected"
startParallelTraining([
  {config: 'default_tbg', phase: 'all'},
  {config: 'case_tbg', phase: 'all'},
  {config: 'six_pack_tbg', phase: 'all'}
]);
```

### 2. Performance Comparison
Add metrics to compare model performance across configs:
- Training loss convergence rates
- Validation accuracy
- Inference speed
- Model size

### 3. Auto-Resume
Automatically resume incomplete training on system restart.

### 4. Training Scheduler
Schedule training jobs to run during off-peak hours:
```javascript
scheduleTraining({
  config: 'complex_sc',
  phase: 'all',
  startTime: '02:00',
  device: 'cuda'
});
```

## Testing the Enhanced UI

### 1. Access the Dashboard
Navigate to: http://172.29.20.187:8088/admin/trm

### 2. Verify Progress Loading
Check that the progress matrix displays with:
- All 7 configurations listed
- Checkmarks for completed phases
- Pending icons for incomplete phases
- Correct overall progress percentages

### 3. Test Config Selection
- Click on different config rows
- Verify the selected config highlights
- Check that the configuration dropdown updates

### 4. Test Training Initiation
- Select a config
- Choose a phase
- Adjust hyperparameters
- Click "Start Training"
- Verify status updates appear

### 5. Monitor Real-Time Updates
- Watch progress bar increment
- Check loss values update
- Verify loss chart renders
- Confirm checkmark appears when phase completes

## Files Modified

### Frontend
- `/frontend/src/components/admin/TRMTrainingPanelEnhanced.jsx` (CREATED)
- `/frontend/src/pages/admin/TRMDashboard.jsx` (MODIFIED)
- `/frontend/src/services/trmApi.js` (MODIFIED)

### Backend
- `/backend/app/api/endpoints/trm.py` (MODIFIED)

### Documentation
- `/TRM_DASHBOARD_ENHANCEMENTS.md` (THIS FILE)

## Summary

The enhanced TRM dashboard provides a comprehensive, config-specific training management system with:

✓ Visual progress tracking for all 7 supply chain configurations
✓ Clear indication of training completion status
✓ Flexible config and phase selection
✓ Real-time training monitoring
✓ Config-specific checkpoint management
✓ Backward-compatible with legacy checkpoints
✓ Clean, intuitive UI for complex training workflows

This enhancement enables systematic training of specialized TRM models for each supply chain topology, with full visibility into training progress and completion status.
