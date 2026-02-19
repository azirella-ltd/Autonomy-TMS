import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSnackbar } from 'notistack';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Button,
  Input,
  Textarea,
  Label,
  FormField,
  Select,
  SelectOption,
  Alert,
  AlertTitle,
  Spinner,
} from '../common';
import { cn } from '../../lib/utils/cn';
import {
  createGameFromConfig as createGameFromConfigService,
  getAllConfigs as getAllConfigsService,
  getSupplyChainConfigById,
} from '../../services/supplyChainConfigService';
import { getModelStatus } from '../../services/modelService';
import * as gameService from '../../services/gameService';

const CreateGameFromConfig = () => {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [configs, setConfigs] = useState([]);
  const [selectedConfig, setSelectedConfig] = useState('');
  const [gameData, setGameData] = useState({
    name: '',
    description: '',
    max_rounds: 52,
    is_public: true
  });
  const [modelStatus, setModelStatus] = useState(null);
  const [configDetails, setConfigDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState(null);

  // Load supply chain configurations
  useEffect(() => {
    const fetchConfigs = async () => {
      try {
        const data = await getAllConfigsService();
        setConfigs(data);
        setLoading(false);
      } catch (error) {
        console.error('Error fetching configurations:', error);
        enqueueSnackbar('Failed to load supply chain configurations', { variant: 'error' });
        setLoading(false);
      }
    };

    fetchConfigs();
  }, [enqueueSnackbar]);

  // Load Autonomy agent model status
  useEffect(() => {
    (async () => {
      try {
        const status = await getModelStatus();
        setModelStatus(status);
      } catch (e) {
        // non-blocking
      }
    })();
  }, []);

  // Update game data when a config is selected
  useEffect(() => {
    if (selectedConfig) {
      const config = configs.find(c => c.id === selectedConfig);
      if (config) {
        setGameData(prev => ({
          ...prev,
          name: `Game - ${config.name}`,
          description: config.description || ''
        }));
      }
      (async () => {
        try {
          setDetailsLoading(true);
          setDetailsError(null);
          const detail = await getSupplyChainConfigById(selectedConfig);
          setConfigDetails(detail);
        } catch (err) {
          console.error('Error loading supply chain details:', err);
          setDetailsError('Unable to load supply chain details');
          setConfigDetails(null);
        } finally {
          setDetailsLoading(false);
        }
      })();
    } else {
      setConfigDetails(null);
      setDetailsError(null);
    }
  }, [selectedConfig, configs]);

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setGameData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedConfig) {
      enqueueSnackbar('Please select a supply chain configuration', { variant: 'warning' });
      return;
    }

    if (!gameData.name.trim()) {
      enqueueSnackbar('Please enter a game name', { variant: 'warning' });
      return;
    }

    setSubmitting(true);

    try {
      // First, create a game configuration from the supply chain config
      const gameConfig = await createGameFromConfigService(selectedConfig, gameData);

      if (gameConfig) {
        // Then create the game using the generated configuration
        const newGame = await gameService.createGame({
          ...gameConfig,
          player_assignments: [
            // Default player assignments can be added here or configured by the user
            { role: 'retailer', player_type: 'human' },
            { role: 'wholesaler', player_type: 'ai' },
            { role: 'distributor', player_type: 'ai' },
            { role: 'manufacturer', player_type: 'ai' },
          ]
        });
        enqueueSnackbar('Game created successfully!', { variant: 'success' });
        navigate(`/scenarios/${newGame.id}`);
        return newGame;
      } else {
        throw new Error('Failed to create game configuration');
      }
    } catch (error) {
      console.error('Error creating game:', error);
      enqueueSnackbar(
        error.response?.data?.detail || 'Failed to create game',
        { variant: 'error' }
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-4">
      {modelStatus && !modelStatus.is_trained && (
        <Alert variant="error" className="mb-4">
          <AlertTitle>Autonomy Agent Not Trained</AlertTitle>
          The Autonomy agent has not yet been trained, so it cannot be used until training completes. You may still select Basic (heuristics) or Autonomy LLM agents.
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Create Game from Supply Chain Configuration</CardTitle>
          <CardDescription>Select a supply chain configuration to create a new game</CardDescription>
        </CardHeader>
        <hr className="border-border" />
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit}>
            <div className="mb-6">
              <FormField label="Supply Chain Configuration" required>
                <Select
                  id="config-select"
                  value={selectedConfig}
                  onChange={(e) => setSelectedConfig(e.target.value)}
                  placeholder="Select a configuration"
                >
                  {configs.map((config) => (
                    <SelectOption key={config.id} value={config.id}>
                      {config.name}
                      {config.is_active && ' (Active)'}
                    </SelectOption>
                  ))}
                </Select>
              </FormField>

              {selectedConfig && (
                <div className="mt-4">
                  <h4 className="text-base font-medium mb-2">
                    Supply Chain Network Overview
                  </h4>
                  {detailsLoading ? (
                    <div className="flex justify-center py-4">
                      <Spinner size="default" />
                    </div>
                  ) : detailsError ? (
                    <Alert variant="warning">{detailsError}</Alert>
                  ) : configDetails ? (
                    <div className="border border-border rounded-md p-4">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <h5 className="text-sm font-medium mb-1">Items</h5>
                          {configDetails.items?.length ? (
                            <ul className="m-0 pl-5 text-sm">
                              {configDetails.items.map((item) => (
                                <li key={item.id}>{item.name}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-muted-foreground">No items defined</p>
                          )}
                        </div>
                        <div>
                          <h5 className="text-sm font-medium mb-1">Markets</h5>
                          {configDetails.markets?.length ? (
                            <ul className="m-0 pl-5 text-sm">
                              {configDetails.markets.map((market) => (
                                <li key={market.id}>{market.name}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-muted-foreground">No markets defined</p>
                          )}
                        </div>
                        <div>
                          <h5 className="text-sm font-medium mb-1">Sites</h5>
                          {configDetails.sites?.length ? (
                            <ul className="m-0 pl-5 text-sm">
                              {Object.entries(
                                configDetails.sites.reduce((acc, site) => {
                                  const type = site.type || 'unknown';
                                  acc[type] = (acc[type] || 0) + 1;
                                  return acc;
                                }, {})
                              ).map(([type, count]) => (
                                <li key={type}>
                                  {type.replace(/_/g, ' ')}: {count}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-muted-foreground">No sites defined</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              )}

              <FormField label="Game Name" required className="mt-4">
                <Input
                  id="name"
                  name="name"
                  value={gameData.name}
                  onChange={handleInputChange}
                  required
                />
              </FormField>

              <FormField label="Description" className="mt-4">
                <Textarea
                  id="description"
                  name="description"
                  value={gameData.description}
                  onChange={handleInputChange}
                  rows={3}
                />
              </FormField>

              <div className="flex gap-4 mt-4">
                <FormField label="Max Rounds" required className="w-40">
                  <Input
                    type="number"
                    id="max_rounds"
                    name="max_rounds"
                    value={gameData.max_rounds}
                    onChange={handleInputChange}
                    min={1}
                    max={1000}
                    required
                  />
                </FormField>

                <div className="flex items-center h-full pt-6">
                  <label className="flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      name="is_public"
                      checked={gameData.is_public}
                      onChange={handleInputChange}
                      className="mr-2 h-4 w-4 rounded border-input text-primary focus:ring-ring"
                    />
                    <span className="text-sm">Public Game</span>
                  </label>
                </div>
              </div>
            </div>

            <div className="mt-8 flex justify-end gap-4">
              <Button
                variant="outline"
                onClick={() => navigate(-1)}
                disabled={submitting}
                type="button"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!selectedConfig || submitting}
                loading={submitting}
              >
                {submitting ? 'Creating...' : 'Create Game'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {selectedConfig && (
        <div className="mt-8">
          <Card>
            <CardHeader>
              <CardTitle>Configuration Preview</CardTitle>
            </CardHeader>
            <hr className="border-border" />
            <CardContent className="pt-4">
              <p className="text-muted-foreground">
                Select a configuration to see a preview of the game settings that will be generated.
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default CreateGameFromConfig;
