import { useCallback, useRef, useState } from 'react';

const cloneValues = (values) => ({ ...(values ?? {}) });

const runValidator = (validate, values, setErrors) => {
  if (typeof validate !== 'function') {
    setErrors({});
    return {};
  }

  const result = validate(values) || {};
  setErrors(result);
  return result;
};

const useFormik = ({ initialValues = {}, validate, onSubmit }) => {
  const [values, setValuesState] = useState(() => cloneValues(initialValues));
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const valuesRef = useRef(values);

  const updateValues = useCallback((updater, shouldValidate = true) => {
    setValuesState((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : cloneValues(updater);
      valuesRef.current = next;
      if (shouldValidate) {
        runValidator(validate, next, setErrors);
      }
      return next;
    });
  }, [validate]);

  const setValues = useCallback((nextValues, shouldValidate = true) => {
    updateValues(nextValues, shouldValidate);
  }, [updateValues]);

  const setFieldValue = useCallback((field, value, shouldValidate = true) => {
    updateValues((prev) => ({ ...(prev ?? {}), [field]: value }), shouldValidate);
  }, [updateValues]);

  const handleChange = useCallback((eventOrPath, maybeValue) => {
    if (typeof eventOrPath === 'string') {
      setFieldValue(eventOrPath, maybeValue, true);
      return;
    }

    const event = eventOrPath;
    const target = event?.target;
    if (!target?.name) {
      return;
    }

    const { name, type, checked, value } = target;
    const resolvedValue = type === 'checkbox' ? checked : value;
    setFieldValue(name, resolvedValue, true);
  }, [setFieldValue]);

  const handleBlur = useCallback((event) => {
    const target = event?.target;
    if (!target?.name) {
      return;
    }

    const { name } = target;
    setTouched((prev) => ({ ...(prev ?? {}), [name]: true }));
    runValidator(validate, valuesRef.current, setErrors);
  }, [validate]);

  const markAllTouched = useCallback(() => {
    const current = valuesRef.current || {};
    const entries = Object.keys(current).reduce((acc, key) => {
      acc[key] = true;
      return acc;
    }, {});
    setTouched((prev) => ({ ...(prev ?? {}), ...entries }));
  }, []);

  const handleSubmit = useCallback(async (event) => {
    if (event?.preventDefault) {
      event.preventDefault();
    }

    markAllTouched();

    const current = valuesRef.current || {};
    const validationErrors = runValidator(validate, current, setErrors);
    if (Object.keys(validationErrors).length > 0) {
      return validationErrors;
    }

    if (typeof onSubmit !== 'function') {
      return {};
    }

    setIsSubmitting(true);
    try {
      await onSubmit(current);
    } finally {
      setIsSubmitting(false);
    }

    return {};
  }, [markAllTouched, onSubmit, validate]);

  const submitForm = useCallback(() => handleSubmit(), [handleSubmit]);

  return {
    values,
    errors,
    touched,
    isSubmitting,
    handleChange,
    handleBlur,
    handleSubmit,
    submitForm,
    setFieldValue,
    setValues,
  };
};

export { useFormik };
export default useFormik;
