import React, { useState, useCallback } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import {
  Button,
  Card,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/common';
import {
  Plus,
  Trash2,
  Pencil,
  Factory,
  Store,
  Truck,
  Package,
} from 'lucide-react';

// Custom node component
const CustomNode = ({ data, selected }) => {
  const getNodeIcon = () => {
    switch (data.type) {
      case 'manufacturer':
        return <Factory className="h-8 w-8" />;
      case 'wholesaler':
        return <Package className="h-8 w-8" />;
      case 'distributor':
        return <Truck className="h-8 w-8" />;
      case 'retailer':
      default:
        return <Store className="h-8 w-8" />;
    }
  };

  return (
    <Card
      className={`p-4 min-w-[180px] text-center ${
        selected ? 'ring-2 ring-primary shadow-lg' : ''
      }`}
    >
      <div className="text-primary mb-2">{getNodeIcon()}</div>
      <p className="font-medium">{data.label}</p>
      <p className="text-sm text-muted-foreground">
        {data.type.charAt(0).toUpperCase() + data.type.slice(1)}
      </p>
      {data.capacity && (
        <p className="text-xs text-muted-foreground mt-1">
          Capacity: {data.capacity}
        </p>
      )}
    </Card>
  );
};

const nodeTypes = {
  custom: CustomNode,
};

const SupplyChain = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([
    {
      id: '1',
      type: 'custom',
      data: { label: 'Manufacturer', type: 'manufacturer', capacity: '1000 units/day' },
      position: { x: 250, y: 25 },
    },
    {
      id: '2',
      type: 'custom',
      data: { label: 'Wholesaler', type: 'wholesaler', capacity: '5000 units' },
      position: { x: 100, y: 200 },
    },
    {
      id: '3',
      type: 'custom',
      data: { label: 'Distributor', type: 'distributor', capacity: '2000 units' },
      position: { x: 400, y: 200 },
    },
    {
      id: '4',
      type: 'custom',
      data: { label: 'Retailer A', type: 'retailer' },
      position: { x: 50, y: 350 },
    },
    {
      id: '5',
      type: 'custom',
      data: { label: 'Retailer B', type: 'retailer' },
      position: { x: 250, y: 350 },
    },
    {
      id: '6',
      type: 'custom',
      data: { label: 'Retailer C', type: 'retailer' },
      position: { x: 450, y: 350 },
    },
  ]);

  const [edges, setEdges, onEdgesChange] = useEdgesState([
    { id: 'e1-2', source: '1', target: '2', label: '2 days' },
    { id: 'e1-3', source: '1', target: '3', label: '3 days' },
    { id: 'e2-4', source: '2', target: '4', label: '1 day' },
    { id: 'e2-5', source: '2', target: '5', label: '1 day' },
    { id: 'e3-5', source: '3', target: '5', label: '2 days' },
    { id: 'e3-6', source: '3', target: '6', label: '2 days' },
  ]);

  const [openDialog, setOpenDialog] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [nodeForm, setNodeForm] = useState({
    label: '',
    type: 'retailer',
    capacity: '',
  });

  const handleNodeClick = (event, node) => {
    setSelectedNode(node);
  };

  const handleAddNode = () => {
    setNodeForm({
      label: '',
      type: 'retailer',
      capacity: '',
    });
    setSelectedNode(null);
    setOpenDialog(true);
  };

  const handleEditNode = () => {
    if (selectedNode) {
      setNodeForm({
        label: selectedNode.data.label,
        type: selectedNode.data.type,
        capacity: selectedNode.data.capacity || '',
      });
      setOpenDialog(true);
    }
  };

  const handleDeleteNode = () => {
    if (selectedNode) {
      setNodes((nds) => nds.filter((node) => node.id !== selectedNode.id));
      setEdges((eds) =>
        eds.filter(
          (edge) =>
            edge.source !== selectedNode.id && edge.target !== selectedNode.id
        )
      );
      setSelectedNode(null);
    }
  };

  const handleSaveNode = () => {
    if (nodeForm.label.trim() === '') return;

    if (selectedNode) {
      // Update existing node
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === selectedNode.id) {
            return {
              ...node,
              data: {
                ...node.data,
                label: nodeForm.label,
                type: nodeForm.type,
                capacity: nodeForm.capacity,
              },
            };
          }
          return node;
        })
      );
    } else {
      // Add new node
      const newNode = {
        id: `node-${Date.now()}`,
        type: 'custom',
        data: {
          label: nodeForm.label,
          type: nodeForm.type,
          capacity: nodeForm.capacity,
        },
        position: { x: Math.random() * 400, y: Math.random() * 400 },
      };
      setNodes((nds) => [...nds, newNode]);
    }
    setOpenDialog(false);
  };

  const onConnect = useCallback(
    (params) => {
      const newEdge = {
        ...params,
        id: `e${params.source}-${params.target}`,
        label: '1 day',
      };
      setEdges((eds) => addEdge(newEdge, eds));
    },
    [setEdges]
  );

  return (
    <div className="h-[calc(100vh-150px)] relative">
      <div className="absolute top-2 left-2 z-10 flex gap-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                onClick={handleAddNode}
                className="bg-white shadow-md"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Add Node</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                onClick={handleEditNode}
                disabled={!selectedNode}
                className="bg-white shadow-md"
              >
                <Pencil className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Edit Node</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                onClick={handleDeleteNode}
                disabled={!selectedNode}
                className="bg-white shadow-md text-destructive hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Delete Node</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>

      <Dialog open={openDialog} onOpenChange={setOpenDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {selectedNode ? 'Edit Node' : 'Add New Node'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <Label htmlFor="node-label">Node Label</Label>
              <Input
                id="node-label"
                value={nodeForm.label}
                onChange={(e) =>
                  setNodeForm({ ...nodeForm, label: e.target.value })
                }
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="node-type">Node Type</Label>
              <select
                id="node-type"
                value={nodeForm.type}
                onChange={(e) =>
                  setNodeForm({ ...nodeForm, type: e.target.value })
                }
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="manufacturer">Manufacturer</option>
                <option value="wholesaler">Wholesaler</option>
                <option value="distributor">Distributor</option>
                <option value="retailer">Retailer</option>
              </select>
            </div>
            <div>
              <Label htmlFor="node-capacity">Capacity (optional)</Label>
              <Input
                id="node-capacity"
                value={nodeForm.capacity}
                onChange={(e) =>
                  setNodeForm({ ...nodeForm, capacity: e.target.value })
                }
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveNode}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SupplyChain;
