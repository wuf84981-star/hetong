import React from 'react';

interface StarRatingProps {
  value: number;
  onChange?: (value: number) => void;
  readonly?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const SIZES = { sm: 'text-base', md: 'text-2xl', lg: 'text-4xl' };

export const StarRating: React.FC<StarRatingProps> = ({
  value, onChange, readonly = false, size = 'md',
}) => (
  <div className="flex gap-1">
    {[1, 2, 3, 4, 5].map(n => (
      <button
        key={n}
        type="button"
        disabled={readonly}
        onClick={() => onChange?.(n)}
        className={`${SIZES[size]} ${
          n <= value ? 'text-yellow-400' : 'text-gray-300'
        } ${readonly ? 'cursor-default' : 'cursor-pointer hover:scale-110'} transition`}
      >
        ★
      </button>
    ))}
  </div>
);

export default StarRating;