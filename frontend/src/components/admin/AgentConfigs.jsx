import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import {
  Button,
  IconButton,
  Card,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Chip,
  Spinner,
  Alert,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
} from '../common';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { api } from '../../services/api';
import AgentConfigForm from './AgentConfigForm';

const AgentConfigs = ({ gameId }) => {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);

  const fetchConfigs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get(`/scenarios/${scenarioId}/agent-configs`);
      setConfigs(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load agent configurations');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this configuration?')) {
      try {
        await api.delete(`/agent-configs/${id}`);
        setConfigs(configs.filter(config => config.id !== id));
      } catch (err) {
        setError('Failed to delete configuration');
        console.error(err);
      }
    }
  };

  const handleSuccess = () => {
    setDialogOpen(false);
    setEditingConfig(null);
    fetchConfigs();
  };

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-lg font-semibold text-foreground">Agent Configurations</h2>
        <Button
          leftIcon={<Plus className="h-4 w-4" />}
          onClick={() => setDialogOpen(true)}
        >
          New Configuration
        </Button>
      </div>

      {error && (
        <Alert variant="error" className="mb-6">
          {error}
        </Alert>
      )}

      <Card padding="none">
        <TableContainer>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Role</TableHead>
                <TableHead>Agent Type</TableHead>
                <TableHead>Configuration</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.length === 0 ? (
                <TableRow hoverable={false}>
                  <TableCell colSpan={4} className="text-center py-8">
                    <span className="text-muted-foreground">
                      No agent configurations found. Create one to get started.
                    </span>
                  </TableCell>
                </TableRow>
              ) : (
                configs.map((config) => (
                  <TableRow key={config.id}>
                    <TableCell>
                      <Chip
                        variant="outline"
                        size="sm"
                      >
                        {config.role}
                      </Chip>
                    </TableCell>
                    <TableCell>
                      <Chip
                        variant="secondary"
                        size="sm"
                      >
                        {config.agent_type.replace('_', ' ')}
                      </Chip>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-[400px] overflow-hidden text-ellipsis">
                        <span className="text-sm truncate block">
                          {JSON.stringify(config.config)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <IconButton
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingConfig(config);
                          setDialogOpen(true);
                        }}
                        className="mr-1"
                      >
                        <Pencil className="h-4 w-4" />
                      </IconButton>
                      <IconButton
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(config.id)}
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 className="h-4 w-4" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      <Modal
        isOpen={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          setEditingConfig(null);
        }}
        size="lg"
      >
        <ModalHeader>
          <ModalTitle>
            {editingConfig ? 'Edit Agent Configuration' : 'Create Agent Configuration'}
          </ModalTitle>
        </ModalHeader>
        <div className="border-t border-border" />
        <ModalBody>
          <AgentConfigForm
            gameId={gameId}
            configId={editingConfig?.id}
            onSuccess={handleSuccess}
          />
        </ModalBody>
      </Modal>
    </div>
  );
};

export default AgentConfigs;
