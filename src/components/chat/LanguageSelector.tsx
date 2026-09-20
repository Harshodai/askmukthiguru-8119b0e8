            {isOpen && coords && (
              <>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="fixed inset-0 z-[90]"
                  onClick={() => setIsOpen(false)}
                />
                <motion.div
                  initial={{ opacity: 0, y: 8, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.95 }}
                  transition={{ duration: 0.15, ease: 'easeOut' }}
                  ref={popoverRef}
                  className="fixed z-[100] flex flex-col overflow-hidden rounded-xl border border-hairline bg-popover shadow-lg w-72 max-w-[calc(100vw-2rem)]"
                  style={{ bottom: coords.bottom, left: coords.left, maxHeight: Math.min(320, coords.maxHeight) }}
                  role="dialog"
                  aria-label={t('chat.selectLanguageAria', 'Select language')}
                >
                  {/* Header */}
                  <div className="px-3 py-2.5 border-b border-border bg-card/95 space-y-2">
                    <div className="flex items-center gap-2">
                      <Globe className="w-3.5 h-3.5 text-ojas" />
                      <span className="text-xs font-semibold text-foreground">{t('chat.selectLanguage', 'Select Language')}</span>
                    </div>
                    <input
                      value={searchQuery}
                      onChange={(e) => {
                        setSearchQuery(e.target.value);
                        setFocusedIndex(0);
                      }}
                      placeholder={t('chat.searchLanguages', { count: LANGUAGES.length })}
                      aria-label={t('chat.searchLanguages', { count: LANGUAGES.length })}
                      className="w-full h-9 rounded-lg border border-border/60 bg-background px-2.5 text-sm outline-none focus:ring-2 focus:ring-ojas/30"
                    />
                  </div>

                  {/* Language list */}
                  <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin" role="listbox" aria-label={t('chat.selectLanguageAria', 'Select language')}>
                    {filteredLanguages.length > 0 ? (
                      <div className="py-1">{renderLanguageRows()}</div>
                    ) : (
                      <p className="px-4 py-6 text-center text-xs text-muted-foreground">
                        {t('chat.noLangMatch', 'No languages match your search.')}
                      </p>
                    )}
                  </div>

                  {/* Translation notice footer */}
                  <div className="px-3 py-2 border-t border-border bg-muted/30 flex items-start gap-2">
                    <Languages className="w-3.5 h-3.5 text-ojas flex-shrink-0 mt-0.5" />
                    <p className="text-[10px] text-muted-foreground leading-relaxed">
                      {t('language.translationNotice')}
                    </p>
                  </div>
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <motion.button
          ref={triggerRef}
          onClick={(e) => {
            e.stopPropagation();
            if (!isOpen) updatePosition();
            setIsOpen(!isOpen);
          }}
          className="flex items-center gap-2 px-3 py-2 min-h-[44px] min-w-[44px] rounded-full bg-card hover:bg-ojas/10 border border-border hover:border-ojas/30 transition-all text-sm shadow-sm"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-label={t('language.ariaLabel', { name: currentLang?.name ?? LANGUAGES[0]?.name ?? 'English' })}
        >
          <Globe className="w-4 h-4 text-ojas" />
          <span className="text-foreground font-medium hidden sm:inline">
{currentLang?.native || selectedLanguage}
          </span>
          <span className="text-foreground font-medium sm:hidden text-base">
            {currentLang?.code.toUpperCase()}
          </span>
        </motion.button>

        <AnimatePresence>
          {isOpen && coords && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[90]"
                onClick={() => setIsOpen(false)}
              />
              <motion.div
                initial={{ opacity: 0, y: -10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                ref={popoverRef}
                className="fixed w-72 max-w-[calc(100vw-2rem)] flex flex-col bg-popover border border-border rounded-2xl shadow-2xl z-[100] overflow-hidden"
                style={{ bottom: coords.bottom, left: coords.left, maxHeight: Math.min(320, coords.maxHeight) }}
                role="dialog"
                aria-label={t('chat.selectLanguageAria', 'Select language')}
              >
                <div className="px-3 py-2.5 border-b border-border bg-card space-y-2">
                  <div className="flex items-center gap-2">
                    <Globe className="w-3.5 h-3.5 text-ojas" />
                    <span className="text-xs font-semibold text-foreground">{t('chat.selectLanguage', 'Select Language')}</span>
                  </div>
                  <input
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setFocusedIndex(0);
                    }}
                    placeholder={t('language.searchPlaceholder')}
                    aria-label={t('language.searchPlaceholder')}
                    className="w-full h-9 rounded-lg border border-border/60 bg-background px-2.5 text-sm outline-none focus:ring-2 focus:ring-ojas/30"
                  />
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin" role="listbox" aria-label={t('chat.selectLanguageAria', 'Select language')}>
                  {filteredLanguages.length > 0 ? (
                    <div className="py-1">{renderLanguageRows()}</div>
                  ) : (
                    <p className="px-4 py-6 text-center text-xs text-muted-foreground">
                      {t('chat.noLangMatch', 'No languages match your search.')}
                    </p>
                  )}
                </div>
                <div className="px-3 py-2 border-t border-border bg-muted/30 flex items-start gap-2">
                  <Languages className="w-3.5 h-3.5 text-ojas flex-shrink-0 mt-0.5" />
                  <p className="text-[10px] text-muted-foreground leading-relaxed">
                    {t('language.translationNotice')}