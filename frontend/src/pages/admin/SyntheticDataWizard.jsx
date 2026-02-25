/**
 * Synthetic Data Generation Wizard
 *
 * A Claude-powered conversational wizard that guides system administrators
 * through creating synthetic supply chain data for testing and demonstration.
 *
 * Features:
 * - Natural language conversation with Claude
 * - Step-by-step guided configuration
 * - Quick selection buttons for common choices
 * - Real-time validation feedback
 * - Progress indicator
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Stepper,
  Step,
  StepLabel,
  Card,
  CardContent,
  CardActions,
  Chip,
  Grid,
  CircularProgress,
  Alert,
  AlertTitle,
  IconButton,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Divider,
  LinearProgress,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  Send as SendIcon,
  SmartToy as BotIcon,
  Person as PersonIcon,
  Store as StoreIcon,
  LocalShipping as ShippingIcon,
  Factory as FactoryIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  ArrowBack as BackIcon,
  PlayArrow as GenerateIcon,
} from '@mui/icons-material';
import { api } from '../../services/api';

// Step definitions for the stepper
const WIZARD_STEPS = [
  { key: 'welcome', label: 'Welcome' },
  { key: 'archetype', label: 'Company Type' },
  { key: 'company_details', label: 'Company Details' },
  { key: 'network_config', label: 'Network' },
  { key: 'product_config', label: 'Products' },
  { key: 'demand_config', label: 'Demand' },
  { key: 'agent_config', label: 'AI Agents' },
  { key: 'review', label: 'Review' },
];

// Archetype icons and colors
const ARCHETYPE_CONFIG = {
  retailer: {
    icon: <StoreIcon fontSize="large" />,
    color: '#4caf50',
    title: 'Retailer',
    description: 'Multi-channel retail operations with focus on availability',
  },
  distributor: {
    icon: <ShippingIcon fontSize="large" />,
    color: '#2196f3',
    title: 'Distributor',
    description: 'Wholesale distribution with focus on OTIF',
  },
  manufacturer: {
    icon: <FactoryIcon fontSize="large" />,
    color: '#ff9800',
    title: 'Manufacturer',
    description: 'Production-focused with multi-tier manufacturing',
  },
};

const SyntheticDataWizard = () => {
  // State
  const [sessionId, setSessionId] = useState(null);
  const [currentStep, setCurrentStep] = useState('welcome');
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [options, setOptions] = useState([]);
  const [state, setState] = useState({});
  const [error, setError] = useState(null);
  const [generationResult, setGenerationResult] = useState(null);
  const [showResultDialog, setShowResultDialog] = useState(false);

  // Refs
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Start session on mount
  useEffect(() => {
    startSession();
  }, []);

  // Get current step index for stepper
  const getCurrentStepIndex = () => {
    const idx = WIZARD_STEPS.findIndex((s) => s.key === currentStep);
    return idx >= 0 ? idx : 0;
  };

  // Start a new wizard session
  const startSession = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.post('/synthetic-data/wizard/sessions');
      const data = response.data;

      setSessionId(data.session_id);
      setCurrentStep(data.step);
      setOptions(data.options || []);
      setState(data.state || {});

      // Add initial message
      if (data.message) {
        setMessages([
          {
            role: 'assistant',
            content: data.message,
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (err) {
      console.error('Failed to start wizard session:', err);
      setError('Failed to start wizard session. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Send a message to the wizard
  const sendMessage = async (message) => {
    if (!message.trim() || !sessionId || isLoading) return;

    setIsLoading(true);
    setError(null);

    // Add user message immediately
    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
      },
    ]);
    setInputValue('');

    try {
      const response = await api.post(
        `/synthetic-data/wizard/sessions/${sessionId}/messages`,
        { message }
      );
      const data = response.data;

      setCurrentStep(data.step);
      setOptions(data.options || []);
      setState(data.state || {});

      // Add assistant response
      if (data.message) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.message,
            timestamp: new Date().toISOString(),
            extracted_data: data.extracted_data,
            validation_errors: data.validation_errors,
          },
        ]);
      }
    } catch (err) {
      console.error('Failed to send message:', err);
      setError('Failed to send message. Please try again.');
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  // Handle form submission
  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(inputValue);
  };

  // Handle quick option selection
  const handleOptionSelect = (option) => {
    const message = option.value || option.label || option;
    sendMessage(message);
  };

  // Generate data
  const handleGenerate = async () => {
    if (!sessionId) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.post(
        `/synthetic-data/wizard/sessions/${sessionId}/generate`
      );
      const data = response.data;

      if (data.success) {
        setGenerationResult(data);
        setShowResultDialog(true);
        setCurrentStep('complete');
      } else {
        setError(data.error || 'Generation failed');
      }
    } catch (err) {
      console.error('Failed to generate data:', err);
      setError('Failed to generate data. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Restart wizard
  const handleRestart = () => {
    setMessages([]);
    setOptions([]);
    setState({});
    setGenerationResult(null);
    setShowResultDialog(false);
    startSession();
  };

  // Render archetype selection cards
  const renderArchetypeCards = () => {
    return (
      <Grid container spacing={2} sx={{ mt: 2, mb: 2 }}>
        {Object.entries(ARCHETYPE_CONFIG).map(([key, config]) => (
          <Grid item xs={12} md={4} key={key}>
            <Card
              sx={{
                cursor: 'pointer',
                border: '2px solid transparent',
                borderColor:
                  state.archetype === key ? config.color : 'transparent',
                '&:hover': {
                  borderColor: config.color,
                  boxShadow: 3,
                },
                transition: 'all 0.2s',
              }}
              onClick={() => handleOptionSelect(key)}
            >
              <CardContent sx={{ textAlign: 'center' }}>
                <Avatar
                  sx={{
                    bgcolor: config.color,
                    width: 64,
                    height: 64,
                    mx: 'auto',
                    mb: 2,
                  }}
                >
                  {config.icon}
                </Avatar>
                <Typography variant="h6" gutterBottom>
                  {config.title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {config.description}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };

  // Render configuration summary
  const renderConfigSummary = () => {
    if (!state || Object.keys(state).length === 0) return null;

    const items = [
      { label: 'Archetype', value: state.archetype },
      { label: 'Company', value: state.company_name },
      { label: 'Customer', value: state.group_name },
      { label: 'Admin', value: state.admin_name },
      { label: 'Sites', value: state.num_sites },
      { label: 'Products', value: state.num_products },
      { label: 'Agent Mode', value: state.agent_mode },
    ].filter((item) => item.value);

    if (items.length === 0) return null;

    return (
      <Paper
        sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}
        variant="outlined"
      >
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          Current Configuration
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {items.map((item, idx) => (
            <Chip
              key={idx}
              label={`${item.label}: ${item.value}`}
              size="small"
              variant="outlined"
            />
          ))}
        </Box>
      </Paper>
    );
  };

  // Render message
  const renderMessage = (msg, idx) => {
    const isUser = msg.role === 'user';

    return (
      <ListItem
        key={idx}
        sx={{
          flexDirection: isUser ? 'row-reverse' : 'row',
          alignItems: 'flex-start',
          py: 1,
        }}
      >
        <ListItemAvatar sx={{ minWidth: 48 }}>
          <Avatar
            sx={{
              bgcolor: isUser ? 'primary.main' : 'secondary.main',
              width: 36,
              height: 36,
            }}
          >
            {isUser ? <PersonIcon /> : <BotIcon />}
          </Avatar>
        </ListItemAvatar>
        <ListItemText
          sx={{
            bgcolor: isUser ? 'primary.light' : 'grey.100',
            borderRadius: 2,
            p: 1.5,
            maxWidth: '80%',
            '& .MuiListItemText-primary': {
              color: isUser ? 'primary.contrastText' : 'text.primary',
            },
          }}
          primary={msg.content}
          secondary={
            msg.validation_errors?.length > 0 && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {msg.validation_errors.join(', ')}
              </Alert>
            )
          }
        />
      </ListItem>
    );
  };

  // Render quick options
  const renderOptions = () => {
    if (!options || options.length === 0) return null;

    return (
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
        {options.map((option, idx) => (
          <Tooltip
            key={idx}
            title={option.description || ''}
            arrow
            placement="top"
          >
            <Button
              variant="outlined"
              size="small"
              onClick={() => handleOptionSelect(option)}
              disabled={isLoading}
            >
              {option.label || option.value || option}
            </Button>
          </Tooltip>
        ))}
      </Box>
    );
  };

  // Render generation result dialog
  const renderResultDialog = () => {
    if (!generationResult) return null;

    return (
      <Dialog
        open={showResultDialog}
        onClose={() => setShowResultDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ bgcolor: 'success.main', color: 'white' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CheckIcon />
            Data Generation Complete
          </Box>
        </DialogTitle>
        <DialogContent sx={{ mt: 2 }}>
          <Typography variant="body1" paragraph>
            Synthetic data has been successfully generated for your supply chain
            configuration.
          </Typography>

          <Grid container spacing={2}>
            <Grid item xs={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Customer ID
              </Typography>
              <Typography variant="h6">{generationResult.customer_id}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Config ID
              </Typography>
              <Typography variant="h6">{generationResult.config_id}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Nodes Created
              </Typography>
              <Typography variant="h6">
                {generationResult.nodes_created}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Lanes Created
              </Typography>
              <Typography variant="h6">
                {generationResult.lanes_created}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Products Created
              </Typography>
              <Typography variant="h6">
                {generationResult.products_created}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Forecasts Created
              </Typography>
              <Typography variant="h6">
                {generationResult.forecasts_created}
              </Typography>
            </Grid>
          </Grid>

          <Alert severity="info" sx={{ mt: 2 }}>
            <AlertTitle>Next Steps</AlertTitle>
            <Typography variant="body2">
              1. Log in with the admin credentials (default password:
              Autonomy@2025)
              <br />
              2. Review the supply chain configuration
              <br />
              3. Run a test game or planning cycle
              <br />
              4. Explore AI agent recommendations
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowResultDialog(false)}>Close</Button>
          <Button
            variant="contained"
            onClick={handleRestart}
            startIcon={<RefreshIcon />}
          >
            Create Another
          </Button>
        </DialogActions>
      </Dialog>
    );
  };

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', p: 3 }}>
      {/* Header */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Synthetic Data Generator
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Create realistic test data for your supply chain planning environment.
          Our AI wizard will guide you through the configuration process.
        </Typography>
      </Paper>

      {/* Stepper */}
      <Stepper
        activeStep={getCurrentStepIndex()}
        alternativeLabel
        sx={{ mb: 3 }}
      >
        {WIZARD_STEPS.map((step) => (
          <Step key={step.key}>
            <StepLabel>{step.label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {/* Error display */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Configuration summary */}
      {renderConfigSummary()}

      {/* Chat interface */}
      <Paper sx={{ mb: 3 }}>
        {/* Messages */}
        <Box
          sx={{
            height: 400,
            overflow: 'auto',
            p: 2,
            bgcolor: 'background.default',
          }}
        >
          {/* Archetype cards shown during selection */}
          {(currentStep === 'welcome' || currentStep === 'archetype') &&
            renderArchetypeCards()}

          {/* Messages list */}
          <List sx={{ py: 0 }}>
            {messages.map((msg, idx) => renderMessage(msg, idx))}
            {isLoading && (
              <ListItem sx={{ justifyContent: 'center' }}>
                <CircularProgress size={24} />
              </ListItem>
            )}
            <div ref={messagesEndRef} />
          </List>
        </Box>

        <Divider />

        {/* Quick options */}
        {options.length > 0 && (
          <Box sx={{ p: 2, bgcolor: 'grey.50' }}>{renderOptions()}</Box>
        )}

        {/* Input form */}
        <Box
          component="form"
          onSubmit={handleSubmit}
          sx={{ p: 2, display: 'flex', gap: 1 }}
        >
          <TextField
            inputRef={inputRef}
            fullWidth
            variant="outlined"
            placeholder="Type your message..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            disabled={isLoading || currentStep === 'complete'}
            size="small"
          />
          <Button
            type="submit"
            variant="contained"
            disabled={!inputValue.trim() || isLoading}
            endIcon={<SendIcon />}
          >
            Send
          </Button>
        </Box>
      </Paper>

      {/* Action buttons */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={handleRestart}
          disabled={isLoading}
        >
          Start Over
        </Button>

        {currentStep === 'review' && (
          <Button
            variant="contained"
            color="success"
            startIcon={<GenerateIcon />}
            onClick={handleGenerate}
            disabled={isLoading}
            size="large"
          >
            Generate Data
          </Button>
        )}
      </Box>

      {/* Result dialog */}
      {renderResultDialog()}
    </Box>
  );
};

export default SyntheticDataWizard;
