import { RotateCcw, SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { ResponsePreferenceMode, ResponsePreferences } from '@/lib/chat/types';

interface ResponsePreferencesMenuProps {
  value: ResponsePreferences;
  onChange: (value: ResponsePreferences) => void;
  onReset: () => void;
}

const MODE_LABELS: Record<ResponsePreferenceMode, string> = {
  balanced_guidance: 'Balanced guidance',
  concise: 'Concise answer',
  reflective_guidance: 'More reflective',
  teaching_explanation: 'Teaching explanation',
};

export const ResponsePreferencesMenu = ({ value, onChange, onReset }: ResponsePreferencesMenuProps) => {
  const { t } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          aria-label={t('chat.responsePreferences', 'Response preferences')}
          title={t('chat.responsePreferences', 'Response preferences')}
        >
          <SlidersHorizontal className="w-4 h-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>
          {t('chat.responsePreferences', 'Response preferences')}
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={value.mode}
          onValueChange={(mode) => onChange({ ...value, mode: mode as ResponsePreferenceMode })}
        >
          {Object.entries(MODE_LABELS).map(([mode, label]) => (
            <DropdownMenuRadioItem key={mode} value={mode}>
              {t(`chat.responseMode.${mode}`, label)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuCheckboxItem
          checked={value.includePractice}
          onCheckedChange={(checked) => onChange({ ...value, includePractice: checked === true })}
        >
          {t('chat.allowPractice', 'Allow one optional practice')}
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={value.includeReflection}
          onCheckedChange={(checked) => onChange({ ...value, includeReflection: checked === true })}
        >
          {t('chat.allowReflection', 'Allow a reflective follow-up')}
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={value.actionDepth === 'one_step'}
          onCheckedChange={(checked) => onChange({ ...value, actionDepth: checked === true ? 'one_step' : 'none' })}
        >
          {t('chat.allowActionStep', 'Allow one action step')}
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onReset}>
          <RotateCcw className="w-4 h-4 mr-2" />
          {t('chat.resetResponsePreferences', 'Reset response preferences')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
