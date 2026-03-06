/**
 * BranchPicker
 *
 * Compact indicator/dropdown for switching between the active baseline
 * config and WORKING branches.  Shows in planning page headers.
 *
 * - Green chip: "Baseline" (default)
 * - Amber chip: "Branch: {name}" (when working on a branch)
 * - Dropdown: list of active WORKING branches + "Create What-If Branch"
 */
import React, { useState } from 'react';
import {
  Box,
  Chip,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Typography,
} from '@mui/material';
import {
  AccountTree as BranchIcon,
  Add as AddIcon,
  Close as CloseIcon,
  CheckCircle as BaselineIcon,
} from '@mui/icons-material';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

export default function BranchPicker() {
  const {
    activeConfig,
    workingBranch,
    branches,
    setWorkingBranch,
    clearWorkingBranch,
    createBranch,
  } = useActiveConfig();

  const [anchorEl, setAnchorEl] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [branchName, setBranchName] = useState('');
  const [branchDesc, setBranchDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const isOnBranch = !!workingBranch;

  const handleChipClick = (e) => setAnchorEl(e.currentTarget);
  const handleClose = () => setAnchorEl(null);

  const handleSelectBranch = (branch) => {
    setWorkingBranch(branch);
    handleClose();
  };

  const handleBackToBaseline = () => {
    clearWorkingBranch();
    handleClose();
  };

  const handleCreateBranch = async () => {
    if (!branchName.trim()) return;
    setCreating(true);
    try {
      await createBranch(branchName.trim(), branchDesc.trim());
      setCreateOpen(false);
      setBranchName('');
      setBranchDesc('');
    } catch (err) {
      console.error('Failed to create branch:', err);
    } finally {
      setCreating(false);
    }
  };

  if (!activeConfig) return null;

  return (
    <>
      <Chip
        icon={isOnBranch ? <BranchIcon /> : <BaselineIcon />}
        label={isOnBranch ? `Branch: ${workingBranch.name}` : `Baseline: ${activeConfig.name}`}
        color={isOnBranch ? 'warning' : 'success'}
        variant="outlined"
        size="small"
        onClick={handleChipClick}
        sx={{ cursor: 'pointer' }}
      />

      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleClose}>
        {/* Back to baseline option */}
        {isOnBranch && (
          <MenuItem onClick={handleBackToBaseline}>
            <ListItemIcon>
              <BaselineIcon fontSize="small" color="success" />
            </ListItemIcon>
            <ListItemText>
              Back to Baseline
              <Typography variant="caption" display="block" color="text.secondary">
                {activeConfig.name}
              </Typography>
            </ListItemText>
          </MenuItem>
        )}

        {/* Existing branches */}
        {branches.length > 0 && <Divider />}
        {branches.map((branch) => (
          <MenuItem
            key={branch.id}
            onClick={() => handleSelectBranch(branch)}
            selected={workingBranch?.id === branch.id}
          >
            <ListItemIcon>
              <BranchIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>{branch.name}</ListItemText>
          </MenuItem>
        ))}

        <Divider />

        {/* Create new branch */}
        <MenuItem
          onClick={() => {
            handleClose();
            setCreateOpen(true);
          }}
        >
          <ListItemIcon>
            <AddIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Create What-If Branch</ListItemText>
        </MenuItem>
      </Menu>

      {/* Create branch dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create What-If Branch</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Creates a copy-on-write branch from the active baseline. Changes on
              the branch do not affect the baseline until committed.
            </Typography>
            <TextField
              label="Branch Name"
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
              placeholder="e.g. Alternate Sourcing — Asia"
              fullWidth
              autoFocus
            />
            <TextField
              label="Description (optional)"
              value={branchDesc}
              onChange={(e) => setBranchDesc(e.target.value)}
              placeholder="What are you testing?"
              fullWidth
              multiline
              rows={2}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} startIcon={<CloseIcon />}>
            Cancel
          </Button>
          <Button
            onClick={handleCreateBranch}
            variant="contained"
            disabled={!branchName.trim() || creating}
            startIcon={<BranchIcon />}
          >
            {creating ? 'Creating...' : 'Create Branch'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
