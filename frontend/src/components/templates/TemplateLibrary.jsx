/**
 * Template Library Component
 * Phase 6 Sprint 4: User Experience Enhancements
 *
 * Browse and search templates with filtering.
 * Features:
 * - Grid/list view
 * - Search and filters
 * - Template preview
 * - Usage tracking
 */

import React, { useState, useEffect } from 'react';
import {
  Search,
  LayoutGrid,
  List,
  Star,
  TrendingUp,
  X,
  Info,
  Play,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import {
  Card,
  CardContent,
  CardFooter,
  Button,
  IconButton,
  Badge,
  Input,
  Label,
  Select,
  SelectOption,
  Alert,
  Spinner,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
} from '../common';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const TemplateLibrary = ({ onSelectTemplate, filterCategory }) => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState(filterCategory || '');
  const [industry, setIndustry] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [showFeatured, setShowFeatured] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 12;

  // View
  const [viewMode, setViewMode] = useState('grid');
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    fetchTemplates();
  }, [searchQuery, category, industry, difficulty, showFeatured, page]);

  const fetchTemplates = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = {
        page,
        page_size: pageSize,
        sort_by: 'usage_count',
        sort_order: 'desc'
      };

      if (searchQuery) params.query = searchQuery;
      if (category) params.category = category;
      if (industry) params.industry = industry;
      if (difficulty) params.difficulty = difficulty;
      if (showFeatured) params.is_featured = true;

      const response = await api.get('/templates', { params });
      setTemplates(response.data.templates);
      setTotal(response.data.total);
      setTotalPages(response.data.total_pages);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch templates');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    setSearchQuery(e.target.value);
    setPage(1);
  };

  const handleFilterChange = (filter, value) => {
    switch (filter) {
      case 'category':
        setCategory(value);
        break;
      case 'industry':
        setIndustry(value);
        break;
      case 'difficulty':
        setDifficulty(value);
        break;
      case 'featured':
        setShowFeatured(value);
        break;
    }
    setPage(1);
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    setCategory(filterCategory || '');
    setIndustry('');
    setDifficulty('');
    setShowFeatured(false);
    setPage(1);
  };

  const handlePreview = (template) => {
    setSelectedTemplate(template);
    setPreviewOpen(true);
  };

  const handleUseTemplate = async (template) => {
    try {
      await api.post(`/templates/${template.id}/use`);
      if (onSelectTemplate) {
        onSelectTemplate(template);
      }
    } catch (err) {
      console.error('Failed to track template usage:', err);
    }
  };

  const TemplateCard = ({ template, compact }) => (
    <Card
      variant="outlined"
      padding="none"
      className="h-full flex flex-col hover:shadow-md transition-shadow"
    >
      <CardContent className="flex-grow p-4">
        <div className="flex justify-between items-start mb-2">
          <h3 className="text-lg font-semibold">
            {template.name}
          </h3>
          {template.is_featured && (
            <Star className="h-4 w-4 text-primary flex-shrink-0" />
          )}
        </div>

        <p className="text-sm text-muted-foreground mb-3">
          {compact
            ? template.short_description || template.description.substring(0, 100) + '...'
            : template.description}
        </p>

        <div className="flex flex-wrap gap-1 mb-2">
          <Badge variant="outline" size="sm">{template.category}</Badge>
          <Badge variant="secondary" size="sm">{template.industry}</Badge>
          <Badge variant="secondary" size="sm">{template.difficulty}</Badge>
        </div>

        {template.tags && template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.tags.slice(0, 3).map((tag, index) => (
              <Badge key={index} variant="outline" size="sm">{tag}</Badge>
            ))}
            {template.tags.length > 3 && (
              <Badge variant="outline" size="sm">+{template.tags.length - 3}</Badge>
            )}
          </div>
        )}

        <div className="flex items-center gap-1 mt-3">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">
            {template.usage_count} uses
          </span>
        </div>
      </CardContent>

      <CardFooter className="p-4 pt-0 gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => handlePreview(template)}
          leftIcon={<Info className="h-4 w-4" />}
        >
          Details
        </Button>
        <Button
          size="sm"
          onClick={() => handleUseTemplate(template)}
          leftIcon={<Play className="h-4 w-4" />}
        >
          Use
        </Button>
      </CardFooter>
    </Card>
  );

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">
          Template Library
        </h1>
        <p className="text-sm text-muted-foreground">
          Browse and use pre-configured templates for your scenarios
        </p>
      </div>

      {/* Search and Filters */}
      <div className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          {/* Search */}
          <div className="md:col-span-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search templates..."
                value={searchQuery}
                onChange={handleSearch}
                className="pl-10"
              />
            </div>
          </div>

          {/* Category Filter */}
          <div className="md:col-span-2">
            <Label className="mb-1 block text-xs">Category</Label>
            <Select
              value={category}
              onChange={(e) => handleFilterChange('category', e.target.value)}
              size="sm"
            >
              <SelectOption value="">All</SelectOption>
              <SelectOption value="distribution">Distribution</SelectOption>
              <SelectOption value="scenario">Scenario</SelectOption>
              <SelectOption value="scenario">Scenario</SelectOption>
              <SelectOption value="supply_chain">Supply Chain</SelectOption>
            </Select>
          </div>

          {/* Industry Filter */}
          <div className="md:col-span-2">
            <Label className="mb-1 block text-xs">Industry</Label>
            <Select
              value={industry}
              onChange={(e) => handleFilterChange('industry', e.target.value)}
              size="sm"
            >
              <SelectOption value="">All</SelectOption>
              <SelectOption value="general">General</SelectOption>
              <SelectOption value="retail">Retail</SelectOption>
              <SelectOption value="manufacturing">Manufacturing</SelectOption>
              <SelectOption value="logistics">Logistics</SelectOption>
              <SelectOption value="healthcare">Healthcare</SelectOption>
              <SelectOption value="technology">Technology</SelectOption>
            </Select>
          </div>

          {/* Difficulty Filter */}
          <div className="md:col-span-2">
            <Label className="mb-1 block text-xs">Difficulty</Label>
            <Select
              value={difficulty}
              onChange={(e) => handleFilterChange('difficulty', e.target.value)}
              size="sm"
            >
              <SelectOption value="">All</SelectOption>
              <SelectOption value="beginner">Beginner</SelectOption>
              <SelectOption value="intermediate">Intermediate</SelectOption>
              <SelectOption value="advanced">Advanced</SelectOption>
              <SelectOption value="expert">Expert</SelectOption>
            </Select>
          </div>

          {/* Featured & View Toggle */}
          <div className="md:col-span-2 flex gap-2">
            <Button
              variant={showFeatured ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleFilterChange('featured', !showFeatured)}
              leftIcon={<Star className="h-4 w-4" />}
            >
              Featured
            </Button>
            <div className="flex border border-input rounded-md">
              <button
                className={cn(
                  'p-2 transition-colors',
                  viewMode === 'grid' ? 'bg-accent' : 'hover:bg-accent/50'
                )}
                onClick={() => setViewMode('grid')}
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                className={cn(
                  'p-2 transition-colors',
                  viewMode === 'list' ? 'bg-accent' : 'hover:bg-accent/50'
                )}
                onClick={() => setViewMode('list')}
              >
                <List className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center mt-4">
          <p className="text-sm text-muted-foreground">
            {total} templates found
          </p>
          {(searchQuery || category || industry || difficulty || showFeatured) && (
            <Button variant="ghost" size="sm" onClick={handleClearFilters}>
              Clear Filters
            </Button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="error" className="mb-4">
          {error}
        </Alert>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-8">
          <Spinner size="lg" />
        </div>
      )}

      {/* Templates Grid/List */}
      {!loading && templates.length > 0 && (
        <>
          <div className={cn(
            'grid gap-4',
            viewMode === 'grid'
              ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
              : 'grid-cols-1'
          )}>
            {templates.map((template) => (
              <TemplateCard key={template.id} template={template} compact={viewMode === 'grid'} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 mt-8">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (page <= 3) {
                  pageNum = i + 1;
                } else if (page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = page - 2 + i;
                }
                return (
                  <Button
                    key={pageNum}
                    variant={page === pageNum ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setPage(pageNum)}
                  >
                    {pageNum}
                  </Button>
                );
              })}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}

      {/* No Results */}
      {!loading && templates.length === 0 && (
        <div className="text-center py-16">
          <h3 className="text-lg font-semibold text-muted-foreground mb-2">
            No templates found
          </h3>
          <p className="text-sm text-muted-foreground">
            Try adjusting your search or filters
          </p>
        </div>
      )}

      {/* Template Preview Dialog */}
      {selectedTemplate && (
        <Modal isOpen={previewOpen} onClose={() => setPreviewOpen(false)} size="lg">
          <ModalHeader>
            <div className="flex justify-between items-start w-full">
              <div>
                <ModalTitle>{selectedTemplate.name}</ModalTitle>
                {selectedTemplate.is_featured && (
                  <Badge className="mt-1">Featured</Badge>
                )}
              </div>
              <Button variant="ghost" size="icon" onClick={() => setPreviewOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </ModalHeader>
          <ModalBody>
            <p className="text-sm mb-4">
              {selectedTemplate.description}
            </p>

            <div className="flex flex-wrap gap-2 mb-4">
              <Badge>{selectedTemplate.category}</Badge>
              <Badge variant="secondary">{selectedTemplate.industry}</Badge>
              <Badge variant="secondary">{selectedTemplate.difficulty}</Badge>
              <Badge variant="outline" icon={<TrendingUp className="h-3 w-3" />}>
                {selectedTemplate.usage_count} uses
              </Badge>
            </div>

            {selectedTemplate.tags && selectedTemplate.tags.length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-muted-foreground mb-1">Tags:</p>
                <div className="flex flex-wrap gap-1">
                  {selectedTemplate.tags.map((tag, index) => (
                    <Badge key={index} variant="outline" size="sm">{tag}</Badge>
                  ))}
                </div>
              </div>
            )}

            {selectedTemplate.configuration && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">Configuration Preview:</p>
                <Card variant="outlined" className="bg-muted/30">
                  <CardContent className="p-3">
                    <pre className="text-xs overflow-auto whitespace-pre-wrap">
                      {JSON.stringify(selectedTemplate.configuration, null, 2)}
                    </pre>
                  </CardContent>
                </Card>
              </div>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={() => setPreviewOpen(false)}>Close</Button>
            <Button
              onClick={() => {
                handleUseTemplate(selectedTemplate);
                setPreviewOpen(false);
              }}
              leftIcon={<Play className="h-4 w-4" />}
            >
              Use Template
            </Button>
          </ModalFooter>
        </Modal>
      )}
    </div>
  );
};

export default TemplateLibrary;
