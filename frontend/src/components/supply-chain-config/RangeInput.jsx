import { Input, Label } from '../common';

const RangeInput = ({
  label,
  value = { min: 0, max: 100 },
  onChange,
  min = 0,
  max = 10000,
  step = 1,
  disabled = false,
}) => {
  const handleMinChange = (e) => {
    const newMin = parseFloat(e.target.value) || 0;
    onChange({ ...value, min: Math.min(newMin, value.max) });
  };

  const handleMaxChange = (e) => {
    const newMax = parseFloat(e.target.value) || 0;
    onChange({ ...value, max: Math.max(newMax, value.min) });
  };

  return (
    <div>
      {label && <p className="text-sm font-medium mb-2">{label}</p>}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="range-min">Min</Label>
          <Input
            id="range-min"
            type="number"
            value={value?.min || ''}
            onChange={handleMinChange}
            min={min}
            max={value?.max}
            step={step}
            disabled={disabled}
          />
        </div>
        <div>
          <Label htmlFor="range-max">Max</Label>
          <Input
            id="range-max"
            type="number"
            value={value?.max || ''}
            onChange={handleMaxChange}
            min={value?.min}
            max={max}
            step={step}
            disabled={disabled}
          />
        </div>
      </div>
    </div>
  );
};

export default RangeInput;
