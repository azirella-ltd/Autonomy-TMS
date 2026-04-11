/**
 * TMS Scenario Templates Page
 *
 * Displays transportation scenario templates as selectable cards grouped
 * by category. Navigates to the CreateScenario wizard with a template
 * query parameter when a template is launched.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
} from '../components/common';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { Play, Users, Bot, Clock, Target } from 'lucide-react';
import { TMS_SCENARIO_TEMPLATES } from '../config/tmsScenarioTemplates';

const CATEGORY_LABELS = {
  procurement: 'Procurement',
  disruption: 'Disruption',
  optimization: 'Optimization',
};

const CATEGORY_ORDER = ['procurement', 'disruption', 'optimization'];

const DIFFICULTY_VARIANT = {
  beginner: 'success',
  intermediate: 'warning',
  advanced: 'destructive',
};

function TemplateCard({ template, onLaunch }) {
  const humanRoles = template.roles.filter((r) => r.type === 'human');
  const aiRoles = template.roles.filter((r) => r.type === 'ai');

  return (
    <Card variant="outlined" padding="none" className="flex flex-col">
      <CardHeader className="p-6 pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-lg">{template.name}</CardTitle>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge variant={DIFFICULTY_VARIANT[template.difficulty]} size="sm">
              {template.difficulty}
            </Badge>
            <Badge variant="outline" size="sm" icon={<Clock className="h-3 w-3" />}>
              {template.estimatedDuration}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-6 pb-6 flex flex-col flex-1 gap-4">
        <p className="text-sm text-muted-foreground">{template.description}</p>

        {/* Roles */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
            <Users className="h-3.5 w-3.5" />
            Roles
          </div>
          <div className="flex flex-wrap gap-1.5">
            {humanRoles.map((role) => (
              <Badge key={role.name} variant="secondary" size="sm" icon={<Users className="h-3 w-3" />}>
                {role.name}
              </Badge>
            ))}
            {aiRoles.map((role) => (
              <Badge key={role.name} variant="outline" size="sm" icon={<Bot className="h-3 w-3" />}>
                {role.name}
              </Badge>
            ))}
          </div>
        </div>

        {/* Objectives */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
            <Target className="h-3.5 w-3.5" />
            Objectives
          </div>
          <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
            {template.objectives.map((obj) => (
              <li key={obj}>{obj}</li>
            ))}
          </ul>
        </div>

        {/* Phases summary */}
        <p className="text-xs text-muted-foreground">
          {template.phases} phases &middot; {template.roles.length} roles ({humanRoles.length} human, {aiRoles.length} AI)
        </p>

        {/* Launch */}
        <div className="mt-auto pt-2">
          <Button
            fullWidth
            leftIcon={<Play className="h-4 w-4" />}
            onClick={() => onLaunch(template.id)}
          >
            Launch Scenario
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CategorySection({ category, templates, onLaunch }) {
  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold text-foreground">
        {CATEGORY_LABELS[category]}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {templates.map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            onLaunch={onLaunch}
          />
        ))}
      </div>
    </section>
  );
}

export default function TMSScenarioTemplates() {
  const navigate = useNavigate();

  const handleLaunch = (templateId) => {
    navigate(`/create-scenario?template=${templateId}`);
  };

  const templatesByCategory = CATEGORY_ORDER.reduce((acc, cat) => {
    const matches = TMS_SCENARIO_TEMPLATES.filter((t) => t.category === cat);
    if (matches.length > 0) {
      acc.push({ category: cat, templates: matches });
    }
    return acc;
  }, []);

  return (
    <div className="space-y-8 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          Transportation Scenarios
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Simulation scenarios for TMS training and strategy testing
        </p>
      </div>

      {/* Category sections */}
      {templatesByCategory.map(({ category, templates }) => (
        <CategorySection
          key={category}
          category={category}
          templates={templates}
          onLaunch={handleLaunch}
        />
      ))}
    </div>
  );
}
