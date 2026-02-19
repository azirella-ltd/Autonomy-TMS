/**
 * Create Game Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import {
  TextInput,
  Button,
  Text,
  Card,
  Chip,
  RadioButton,
  HelperText,
  ProgressBar,
  Divider,
  IconButton,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import { createGame, startGame } from '../../store/slices/gamesSlice';
import { fetchTemplates } from '../../store/slices/templatesSlice';
import { theme } from '../../theme';

const STEPS = [
  { label: 'Game Info', icon: 'information' },
  { label: 'Configuration', icon: 'cog' },
  { label: 'Players', icon: 'account-group' },
  { label: 'Settings', icon: 'tune' },
];

const AGENT_STRATEGIES = [
  { value: 'naive', label: 'Naive', description: 'Mirrors incoming demand' },
  { value: 'conservative', label: 'Conservative', description: 'Maintains stable orders' },
  { value: 'bullwhip', label: 'Bullwhip', description: 'Demonstrates volatility' },
  { value: 'ml_forecast', label: 'ML Forecast', description: 'Machine learning based' },
  { value: 'optimizer', label: 'Optimizer', description: 'Cost optimization' },
  { value: 'llm', label: 'LLM Agent', description: 'GPT-powered decision making' },
];

export default function CreateGameScreen({ navigation }: any) {
  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    configId: null as number | null,
    maxRounds: '52',
    players: [] as Array<{
      nodeName: string;
      isHuman: boolean;
      agentStrategy?: string;
    }>,
    autoStart: false,
  });
  const [errors, setErrors] = useState({
    name: '',
    configId: '',
    players: '',
  });

  const dispatch = useAppDispatch();
  const { templates, loading: templatesLoading } = useAppSelector(
    (state) => state.templates
  );
  const { loading: gamesLoading } = useAppSelector((state) => state.games);

  useEffect(() => {
    // Load templates for configuration selection
    dispatch(fetchTemplates({ page: 1, page_size: 50 }));
  }, [dispatch]);

  const updateFormData = (field: string, value: any) => {
    setFormData({ ...formData, [field]: value });
    setErrors({ ...errors, [field]: '' });
  };

  const validateStep = (step: number): boolean => {
    const newErrors = { name: '', configId: '', players: '' };
    let isValid = true;

    switch (step) {
      case 0: // Game Info
        if (!formData.name.trim()) {
          newErrors.name = 'Game name is required';
          isValid = false;
        }
        break;

      case 1: // Configuration
        if (!formData.configId) {
          newErrors.configId = 'Please select a supply chain configuration';
          isValid = false;
        }
        break;

      case 2: // Players
        if (formData.players.length === 0) {
          newErrors.players = 'Please configure at least one player';
          isValid = false;
        }
        break;

      case 3: // Settings
        // Validation for settings if needed
        break;
    }

    setErrors(newErrors);
    return isValid;
  };

  const handleNext = () => {
    if (validateStep(currentStep)) {
      if (currentStep < STEPS.length - 1) {
        setCurrentStep(currentStep + 1);
      }
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = async () => {
    if (!validateStep(currentStep)) {
      return;
    }

    try {
      // Create game
      const result = await dispatch(
        createGame({
          name: formData.name,
          description: formData.description,
          supply_chain_config_id: formData.configId!,
          max_rounds: parseInt(formData.maxRounds),
          players: formData.players.map((p) => ({
            node_name: p.nodeName,
            is_human: p.isHuman,
            agent_strategy: p.agentStrategy,
          })),
        })
      ).unwrap();

      // Auto-start if requested
      if (formData.autoStart && result.id) {
        await dispatch(startGame(result.id)).unwrap();
      }

      // Navigate to game detail
      navigation.navigate('GameDetail', { gameId: result.id });
    } catch (error: any) {
      console.error('Failed to create game:', error);
    }
  };

  const handleConfigSelect = (configId: number) => {
    updateFormData('configId', configId);

    // Auto-populate players based on selected config
    const config = templates.find((t) => t.id === configId);
    if (config && config.nodes) {
      const players = config.nodes.map((node: any) => ({
        nodeName: node.name,
        isHuman: false,
        agentStrategy: 'naive',
      }));
      updateFormData('players', players);
    }
  };

  const handlePlayerToggle = (index: number) => {
    const players = [...formData.players];
    players[index].isHuman = !players[index].isHuman;
    if (!players[index].isHuman && !players[index].agentStrategy) {
      players[index].agentStrategy = 'naive';
    }
    updateFormData('players', players);
  };

  const handleStrategyChange = (index: number, strategy: string) => {
    const players = [...formData.players];
    players[index].agentStrategy = strategy;
    updateFormData('players', players);
  };

  const progress = (currentStep + 1) / STEPS.length;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Create New Game</Text>
        <Text style={styles.stepIndicator}>
          Step {currentStep + 1} of {STEPS.length}
        </Text>
        <ProgressBar progress={progress} color={theme.colors.primary} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* Step 0: Game Info */}
        {currentStep === 0 && (
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>Game Information</Text>
            <Text style={styles.stepDescription}>
              Provide basic information about your game
            </Text>

            <TextInput
              label="Game Name *"
              value={formData.name}
              onChangeText={(text) => updateFormData('name', text)}
              mode="outlined"
              error={!!errors.name}
              style={styles.input}
            />
            {errors.name ? (
              <HelperText type="error" visible={!!errors.name}>
                {errors.name}
              </HelperText>
            ) : null}

            <TextInput
              label="Description (Optional)"
              value={formData.description}
              onChangeText={(text) => updateFormData('description', text)}
              mode="outlined"
              multiline
              numberOfLines={4}
              style={styles.input}
            />

            <Card style={styles.infoCard}>
              <Card.Content>
                <View style={styles.infoRow}>
                  <IconButton icon="information" size={20} />
                  <Text style={styles.infoText}>
                    Give your game a descriptive name to help you identify it later
                  </Text>
                </View>
              </Card.Content>
            </Card>
          </View>
        )}

        {/* Step 1: Configuration */}
        {currentStep === 1 && (
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>Supply Chain Configuration</Text>
            <Text style={styles.stepDescription}>
              Select a supply chain configuration template
            </Text>

            {templatesLoading ? (
              <Text style={styles.loadingText}>Loading configurations...</Text>
            ) : (
              <>
                {templates.map((template) => (
                  <Card
                    key={template.id}
                    style={[
                      styles.configCard,
                      formData.configId === template.id && styles.selectedCard,
                    ]}
                    onPress={() => handleConfigSelect(template.id)}
                  >
                    <Card.Content>
                      <View style={styles.configHeader}>
                        <View style={styles.configInfo}>
                          <Text style={styles.configName}>{template.name}</Text>
                          <Text style={styles.configDescription} numberOfLines={2}>
                            {template.description}
                          </Text>
                        </View>
                        <RadioButton
                          value={template.id.toString()}
                          status={
                            formData.configId === template.id ? 'checked' : 'unchecked'
                          }
                          onPress={() => handleConfigSelect(template.id)}
                        />
                      </View>
                      <View style={styles.configMeta}>
                        <Chip icon="layers" compact style={styles.metaChip}>
                          {template.difficulty}
                        </Chip>
                        <Chip icon="fire" compact style={styles.metaChip}>
                          {template.usage_count} uses
                        </Chip>
                      </View>
                    </Card.Content>
                  </Card>
                ))}
              </>
            )}

            {errors.configId ? (
              <HelperText type="error" visible={!!errors.configId}>
                {errors.configId}
              </HelperText>
            ) : null}
          </View>
        )}

        {/* Step 2: Players */}
        {currentStep === 2 && (
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>Configure Players</Text>
            <Text style={styles.stepDescription}>
              Assign human or AI players to each node
            </Text>

            {formData.players.length === 0 ? (
              <Card style={styles.infoCard}>
                <Card.Content>
                  <Text style={styles.infoText}>
                    Select a configuration in the previous step to see available nodes
                  </Text>
                </Card.Content>
              </Card>
            ) : (
              formData.players.map((player, index) => (
                <Card key={index} style={styles.playerCard}>
                  <Card.Content>
                    <View style={styles.playerHeader}>
                      <Text style={styles.playerNodeName}>{player.nodeName}</Text>
                      <Chip
                        icon={player.isHuman ? 'account' : 'robot'}
                        onPress={() => handlePlayerToggle(index)}
                        style={styles.playerTypeChip}
                      >
                        {player.isHuman ? 'Human' : 'AI'}
                      </Chip>
                    </View>

                    {!player.isHuman && (
                      <>
                        <Divider style={styles.divider} />
                        <Text style={styles.strategyLabel}>AI Strategy:</Text>
                        <View style={styles.strategyGrid}>
                          {AGENT_STRATEGIES.map((strategy) => (
                            <Chip
                              key={strategy.value}
                              selected={player.agentStrategy === strategy.value}
                              onPress={() => handleStrategyChange(index, strategy.value)}
                              style={styles.strategyChip}
                            >
                              {strategy.label}
                            </Chip>
                          ))}
                        </View>
                        {player.agentStrategy && (
                          <Text style={styles.strategyDescription}>
                            {
                              AGENT_STRATEGIES.find(
                                (s) => s.value === player.agentStrategy
                              )?.description
                            }
                          </Text>
                        )}
                      </>
                    )}
                  </Card.Content>
                </Card>
              ))
            )}

            {errors.players ? (
              <HelperText type="error" visible={!!errors.players}>
                {errors.players}
              </HelperText>
            ) : null}
          </View>
        )}

        {/* Step 3: Settings */}
        {currentStep === 3 && (
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>Game Settings</Text>
            <Text style={styles.stepDescription}>
              Configure game parameters
            </Text>

            <TextInput
              label="Maximum Rounds"
              value={formData.maxRounds}
              onChangeText={(text) => updateFormData('maxRounds', text)}
              mode="outlined"
              keyboardType="numeric"
              style={styles.input}
            />
            <HelperText type="info">
              Typical games run for 36-52 rounds
            </HelperText>

            <Card style={styles.settingCard}>
              <Card.Content>
                <View style={styles.settingRow}>
                  <View style={styles.settingInfo}>
                    <Text style={styles.settingLabel}>Auto-start game</Text>
                    <Text style={styles.settingDescription}>
                      Start the game immediately after creation
                    </Text>
                  </View>
                  <RadioButton
                    value="auto-start"
                    status={formData.autoStart ? 'checked' : 'unchecked'}
                    onPress={() => updateFormData('autoStart', !formData.autoStart)}
                  />
                </View>
              </Card.Content>
            </Card>

            <Card style={styles.summaryCard}>
              <Card.Title title="Summary" titleStyle={styles.summaryTitle} />
              <Card.Content>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Name:</Text>
                  <Text style={styles.summaryValue}>{formData.name}</Text>
                </View>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Configuration:</Text>
                  <Text style={styles.summaryValue}>
                    {templates.find((t) => t.id === formData.configId)?.name || 'N/A'}
                  </Text>
                </View>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Players:</Text>
                  <Text style={styles.summaryValue}>{formData.players.length}</Text>
                </View>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Max Rounds:</Text>
                  <Text style={styles.summaryValue}>{formData.maxRounds}</Text>
                </View>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Auto-start:</Text>
                  <Text style={styles.summaryValue}>
                    {formData.autoStart ? 'Yes' : 'No'}
                  </Text>
                </View>
              </Card.Content>
            </Card>
          </View>
        )}
      </ScrollView>

      {/* Navigation Buttons */}
      <View style={styles.footer}>
        <Button
          mode="outlined"
          onPress={handleBack}
          disabled={currentStep === 0 || gamesLoading}
          style={styles.backButton}
        >
          Back
        </Button>
        {currentStep < STEPS.length - 1 ? (
          <Button
            mode="contained"
            onPress={handleNext}
            disabled={gamesLoading}
            style={styles.nextButton}
          >
            Next
          </Button>
        ) : (
          <Button
            mode="contained"
            onPress={handleSubmit}
            loading={gamesLoading}
            disabled={gamesLoading}
            style={styles.nextButton}
          >
            Create Game
          </Button>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  header: {
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.disabled,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  stepIndicator: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.sm,
  },
  scrollContent: {
    padding: theme.spacing.md,
    paddingBottom: 100,
  },
  stepContent: {
    flex: 1,
  },
  stepTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  stepDescription: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.lg,
  },
  input: {
    marginBottom: theme.spacing.sm,
  },
  infoCard: {
    marginTop: theme.spacing.md,
    backgroundColor: theme.colors.info + '20',
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  infoText: {
    flex: 1,
    fontSize: 14,
    color: theme.colors.text,
  },
  loadingText: {
    textAlign: 'center',
    color: theme.colors.textSecondary,
    padding: theme.spacing.xl,
  },
  configCard: {
    marginBottom: theme.spacing.sm,
  },
  selectedCard: {
    borderWidth: 2,
    borderColor: theme.colors.primary,
  },
  configHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  configInfo: {
    flex: 1,
  },
  configName: {
    fontSize: 16,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: 4,
  },
  configDescription: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  configMeta: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  metaChip: {
    marginRight: theme.spacing.xs,
  },
  playerCard: {
    marginBottom: theme.spacing.sm,
  },
  playerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  playerNodeName: {
    fontSize: 16,
    fontWeight: '600',
    color: theme.colors.text,
  },
  playerTypeChip: {
    backgroundColor: theme.colors.primary + '20',
  },
  divider: {
    marginVertical: theme.spacing.sm,
  },
  strategyLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.sm,
  },
  strategyGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  strategyChip: {
    marginRight: theme.spacing.xs,
    marginBottom: theme.spacing.xs,
  },
  strategyDescription: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    fontStyle: 'italic',
  },
  settingCard: {
    marginVertical: theme.spacing.md,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  settingInfo: {
    flex: 1,
  },
  settingLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: 4,
  },
  settingDescription: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  summaryCard: {
    marginTop: theme.spacing.lg,
    backgroundColor: theme.colors.primary + '10',
  },
  summaryTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
  },
  summaryLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  summaryValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
  },
  footer: {
    flexDirection: 'row',
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderTopWidth: 1,
    borderTopColor: theme.colors.disabled,
    gap: theme.spacing.sm,
  },
  backButton: {
    flex: 1,
  },
  nextButton: {
    flex: 2,
  },
});
