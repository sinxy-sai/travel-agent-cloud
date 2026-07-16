import enUS from './locales/en-US.json';
import zhCN from './locales/zh-CN.json';

export type AppLanguage = 'en-US' | 'zh-CN';
export type TranslationKey = Exclude<keyof typeof enUS, 'options'>;

export const languageStorageKey = 'travel-agent-cloud.language';

export const languageOptions = [
  { value: 'en-US', label: 'English' },
  { value: 'zh-CN', label: '\u4e2d\u6587' },
] satisfies { value: AppLanguage; label: string }[];

const translations = {
  'en-US': enUS,
  'zh-CN': zhCN,
} satisfies Record<AppLanguage, typeof enUS>;

export function normalizeLanguage(value: string | null | undefined): AppLanguage {
  return value === 'zh-CN' || value === 'en-US' ? value : 'en-US';
}

export function translate(language: AppLanguage, key: TranslationKey): string {
  return translations[language][key];
}

export function getLocaleOptions(language: AppLanguage): typeof enUS.options {
  return translations[language].options;
}
