/**
 * Template Library Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  Modal,
} from 'react-native';
import {
  Card,
  Text,
  Searchbar,
  Chip,
  Button,
  ActivityIndicator,
  Avatar,
  Divider,
  IconButton,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  fetchTemplates,
  fetchFeaturedTemplates,
  setFilters,
  clearFilters,
  useTemplate,
} from '../../store/slices/templatesSlice';
import { theme } from '../../theme';

const CATEGORIES = [
  { label: 'All', value: '' },
  { label: 'Manufacturing', value: 'manufacturing' },
  { label: 'Retail', value: 'retail' },
  { label: 'Distribution', value: 'distribution' },
  { label: 'Healthcare', value: 'healthcare' },
];

const DIFFICULTIES = [
  { label: 'All', value: '' },
  { label: 'Beginner', value: 'beginner' },
  { label: 'Intermediate', value: 'intermediate' },
  { label: 'Advanced', value: 'advanced' },
];

interface TemplateCardProps {
  template: any;
  onPress: () => void;
  onUse: () => void;
}

const TemplateCard = ({ template, onPress, onUse }: TemplateCardProps) => {
  const difficultyColor =
    template.difficulty === 'beginner'
      ? theme.colors.success
      : template.difficulty === 'intermediate'
      ? theme.colors.warning
      : theme.colors.error;

  return (
    <TouchableOpacity onPress={onPress}>
      <Card style={styles.templateCard}>
        <Card.Content>
          <View style={styles.cardHeader}>
            <View style={styles.cardTitleContainer}>
              <Text style={styles.templateName} numberOfLines={1}>
                {template.name}
              </Text>
              {template.is_featured && (
                <Avatar.Icon
                  size={24}
                  icon="star"
                  style={styles.featuredIcon}
                />
              )}
            </View>
          </View>

          <Text style={styles.templateDescription} numberOfLines={2}>
            {template.description}
          </Text>

          <View style={styles.metaContainer}>
            <Chip
              icon="layers"
              compact
              style={[styles.difficultyChip, { backgroundColor: difficultyColor + '20' }]}
              textStyle={{ color: difficultyColor }}
            >
              {template.difficulty}
            </Chip>
            {template.category && (
              <Chip icon="tag" compact style={styles.metaChip}>
                {template.category}
              </Chip>
            )}
            {template.industry && (
              <Chip icon="domain" compact style={styles.metaChip}>
                {template.industry}
              </Chip>
            )}
          </View>

          <View style={styles.statsContainer}>
            <View style={styles.statItem}>
              <IconButton icon="fire" size={16} style={styles.statIcon} />
              <Text style={styles.statText}>{template.usage_count} uses</Text>
            </View>
            {template.tags && template.tags.length > 0 && (
              <View style={styles.statItem}>
                <IconButton icon="tag-multiple" size={16} style={styles.statIcon} />
                <Text style={styles.statText}>{template.tags.length} tags</Text>
              </View>
            )}
          </View>

          <Divider style={styles.divider} />

          <Button
            mode="contained"
            icon="play"
            onPress={onUse}
            style={styles.useButton}
          >
            Use Template
          </Button>
        </Card.Content>
      </Card>
    </TouchableOpacity>
  );
};

export default function TemplateLibraryScreen({ navigation }: any) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const dispatch = useAppDispatch();
  const {
    templates,
    featuredTemplates,
    loading,
    filters,
    page,
    totalPages,
  } = useAppSelector((state) => state.templates);

  useEffect(() => {
    loadTemplates();
    dispatch(fetchFeaturedTemplates());
  }, []);

  useEffect(() => {
    // Reload when filters change
    loadTemplates();
  }, [filters.category, filters.difficulty]);

  const loadTemplates = () => {
    dispatch(
      fetchTemplates({
        page: 1,
        query: searchQuery,
        category: filters.category,
        difficulty: filters.difficulty,
      })
    );
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadTemplates();
    await dispatch(fetchFeaturedTemplates());
    setRefreshing(false);
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    if (query.length === 0 || query.length >= 3) {
      dispatch(fetchTemplates({ page: 1, query }));
    }
  };

  const handleCategoryFilter = (category: string) => {
    dispatch(setFilters({ category }));
  };

  const handleDifficultyFilter = (difficulty: string) => {
    dispatch(setFilters({ difficulty }));
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    dispatch(clearFilters());
  };

  const handleLoadMore = () => {
    if (!loading && page < totalPages) {
      dispatch(
        fetchTemplates({
          page: page + 1,
          query: searchQuery,
          category: filters.category,
          difficulty: filters.difficulty,
        })
      );
    }
  };

  const handleTemplatePress = (template: any) => {
    setSelectedTemplate(template);
    setModalVisible(true);
  };

  const handleUseTemplate = (template: any) => {
    // Mark template as used
    dispatch(useTemplate(template.id));

    // Navigate to create game with template pre-selected
    navigation.navigate('Games', {
      screen: 'CreateGame',
      params: { templateId: template.id },
    });
  };

  const renderItem = ({ item }: { item: any }) => (
    <TemplateCard
      template={item}
      onPress={() => handleTemplatePress(item)}
      onUse={() => handleUseTemplate(item)}
    />
  );

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Avatar.Icon
        size={80}
        icon="file-multiple-outline"
        style={styles.emptyIcon}
      />
      <Text style={styles.emptyTitle}>No Templates Found</Text>
      <Text style={styles.emptySubtitle}>
        Try adjusting your search or filters
      </Text>
      <Button mode="outlined" onPress={handleClearFilters} style={styles.clearButton}>
        Clear Filters
      </Button>
    </View>
  );

  const renderFooter = () => {
    if (!loading) return null;
    return (
      <View style={styles.footerLoader}>
        <ActivityIndicator size="small" color={theme.colors.primary} />
      </View>
    );
  };

  const hasActiveFilters =
    searchQuery || filters.category || filters.difficulty;

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <Searchbar
        placeholder="Search templates..."
        onChangeText={handleSearch}
        value={searchQuery}
        style={styles.searchBar}
      />

      {/* Featured Section */}
      {!hasActiveFilters && featuredTemplates.length > 0 && (
        <View style={styles.featuredSection}>
          <Text style={styles.sectionTitle}>Featured Templates</Text>
          <FlatList
            data={featuredTemplates.slice(0, 5)}
            renderItem={renderItem}
            keyExtractor={(item) => `featured-${item.id}`}
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.featuredList}
          />
        </View>
      )}

      {/* Category Filter */}
      <View style={styles.filtersContainer}>
        <Text style={styles.filterLabel}>Category:</Text>
        <View style={styles.filterChips}>
          {CATEGORIES.map((cat) => (
            <Chip
              key={cat.value}
              selected={filters.category === cat.value}
              onPress={() => handleCategoryFilter(cat.value)}
              style={styles.filterChip}
            >
              {cat.label}
            </Chip>
          ))}
        </View>
      </View>

      {/* Difficulty Filter */}
      <View style={styles.filtersContainer}>
        <Text style={styles.filterLabel}>Difficulty:</Text>
        <View style={styles.filterChips}>
          {DIFFICULTIES.map((diff) => (
            <Chip
              key={diff.value}
              selected={filters.difficulty === diff.value}
              onPress={() => handleDifficultyFilter(diff.value)}
              style={styles.filterChip}
            >
              {diff.label}
            </Chip>
          ))}
        </View>
      </View>

      {/* Templates List */}
      <FlatList
        data={templates}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.5}
        ListEmptyComponent={!loading ? renderEmpty : null}
        ListFooterComponent={renderFooter}
      />

      {/* Template Detail Modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setModalVisible(false)}
      >
        {selectedTemplate && (
          <View style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{selectedTemplate.name}</Text>
              <IconButton
                icon="close"
                size={24}
                onPress={() => setModalVisible(false)}
              />
            </View>

            <View style={styles.modalContent}>
              <Text style={styles.modalDescription}>
                {selectedTemplate.description}
              </Text>

              <View style={styles.modalMetaContainer}>
                <View style={styles.modalMetaRow}>
                  <Text style={styles.modalMetaLabel}>Category:</Text>
                  <Text style={styles.modalMetaValue}>
                    {selectedTemplate.category || 'N/A'}
                  </Text>
                </View>
                <View style={styles.modalMetaRow}>
                  <Text style={styles.modalMetaLabel}>Industry:</Text>
                  <Text style={styles.modalMetaValue}>
                    {selectedTemplate.industry || 'N/A'}
                  </Text>
                </View>
                <View style={styles.modalMetaRow}>
                  <Text style={styles.modalMetaLabel}>Difficulty:</Text>
                  <Text style={styles.modalMetaValue}>
                    {selectedTemplate.difficulty}
                  </Text>
                </View>
                <View style={styles.modalMetaRow}>
                  <Text style={styles.modalMetaLabel}>Usage Count:</Text>
                  <Text style={styles.modalMetaValue}>
                    {selectedTemplate.usage_count}
                  </Text>
                </View>
              </View>

              {selectedTemplate.tags && selectedTemplate.tags.length > 0 && (
                <View style={styles.tagsContainer}>
                  <Text style={styles.tagsLabel}>Tags:</Text>
                  <View style={styles.tagsChips}>
                    {selectedTemplate.tags.map((tag: string, index: number) => (
                      <Chip key={index} compact style={styles.tagChip}>
                        {tag}
                      </Chip>
                    ))}
                  </View>
                </View>
              )}
            </View>

            <View style={styles.modalFooter}>
              <Button
                mode="outlined"
                onPress={() => setModalVisible(false)}
                style={styles.modalCancelButton}
              >
                Cancel
              </Button>
              <Button
                mode="contained"
                icon="play"
                onPress={() => {
                  setModalVisible(false);
                  handleUseTemplate(selectedTemplate);
                }}
                style={styles.modalUseButton}
              >
                Use Template
              </Button>
            </View>
          </View>
        )}
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  searchBar: {
    margin: theme.spacing.md,
    elevation: 2,
  },
  featuredSection: {
    marginBottom: theme.spacing.md,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: theme.colors.text,
    paddingHorizontal: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  featuredList: {
    paddingHorizontal: theme.spacing.md,
  },
  filtersContainer: {
    paddingHorizontal: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  filterLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  filterChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
  },
  filterChip: {
    marginRight: theme.spacing.xs,
  },
  listContent: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  templateCard: {
    marginBottom: theme.spacing.md,
    marginRight: theme.spacing.md,
    width: 300,
  },
  cardHeader: {
    marginBottom: theme.spacing.sm,
  },
  cardTitleContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  templateName: {
    fontSize: 18,
    fontWeight: '600',
    color: theme.colors.text,
    flex: 1,
  },
  featuredIcon: {
    backgroundColor: theme.colors.warning,
    marginLeft: theme.spacing.xs,
  },
  templateDescription: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.sm,
    minHeight: 40,
  },
  metaContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
  },
  difficultyChip: {
    marginRight: theme.spacing.xs,
  },
  metaChip: {
    marginRight: theme.spacing.xs,
  },
  statsContainer: {
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  statItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statIcon: {
    margin: 0,
  },
  statText: {
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  divider: {
    marginVertical: theme.spacing.sm,
  },
  useButton: {
    marginTop: theme.spacing.xs,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.xl * 2,
  },
  emptyIcon: {
    backgroundColor: theme.colors.disabled,
    marginBottom: theme.spacing.lg,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  emptySubtitle: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    textAlign: 'center',
    marginBottom: theme.spacing.lg,
  },
  clearButton: {
    marginTop: theme.spacing.sm,
  },
  footerLoader: {
    paddingVertical: theme.spacing.md,
  },
  modalContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: theme.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.disabled,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: theme.colors.text,
    flex: 1,
  },
  modalContent: {
    flex: 1,
    padding: theme.spacing.lg,
  },
  modalDescription: {
    fontSize: 16,
    color: theme.colors.text,
    marginBottom: theme.spacing.lg,
    lineHeight: 24,
  },
  modalMetaContainer: {
    marginBottom: theme.spacing.lg,
  },
  modalMetaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.disabled,
  },
  modalMetaLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.textSecondary,
  },
  modalMetaValue: {
    fontSize: 14,
    color: theme.colors.text,
  },
  tagsContainer: {
    marginTop: theme.spacing.md,
  },
  tagsLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.sm,
  },
  tagsChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
  },
  tagChip: {
    marginRight: theme.spacing.xs,
    marginBottom: theme.spacing.xs,
  },
  modalFooter: {
    flexDirection: 'row',
    padding: theme.spacing.md,
    borderTopWidth: 1,
    borderTopColor: theme.colors.disabled,
    gap: theme.spacing.sm,
  },
  modalCancelButton: {
    flex: 1,
  },
  modalUseButton: {
    flex: 2,
  },
});
