import React from 'react';
import {
  Button,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './common';
import { Download } from 'lucide-react';

const FilterBar = () => {
  const [quarter, setQuarter] = React.useState('Q1');
  const [year, setYear] = React.useState('2025');
  const [scope, setScope] = React.useState('All SKU');
  const [granularity, setGranularity] = React.useState('Weekly');

  return (
    <div className="mb-4">
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-end">
        <div className="md:col-span-8">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="min-w-[110px]">
              <Label htmlFor="quarter-select" className="text-xs">Quarter</Label>
              <Select value={quarter} onValueChange={setQuarter}>
                <SelectTrigger id="quarter-select" className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['Q1', 'Q2', 'Q3', 'Q4'].map(q => (
                    <SelectItem key={q} value={q}>{q}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-[110px]">
              <Label htmlFor="year-select" className="text-xs">Year</Label>
              <Select value={year} onValueChange={setYear}>
                <SelectTrigger id="year-select" className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['2024', '2025', '2026'].map(y => (
                    <SelectItem key={y} value={y}>{y}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-[140px]">
              <Label htmlFor="scope-select" className="text-xs">Scope</Label>
              <Select value={scope} onValueChange={setScope}>
                <SelectTrigger id="scope-select" className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['All SKU', 'Top 20', 'Category A'].map(s => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-[140px]">
              <Label htmlFor="granularity-select" className="text-xs">Granularity</Label>
              <Select value={granularity} onValueChange={setGranularity}>
                <SelectTrigger id="granularity-select" className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['Daily', 'Weekly', 'Monthly'].map(g => (
                    <SelectItem key={g} value={g}>{g}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <div className="md:col-span-4">
          <div className="flex justify-start md:justify-end gap-2">
            <Button variant="outline" leftIcon={<Download className="h-4 w-4" />}>
              Export
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FilterBar;
