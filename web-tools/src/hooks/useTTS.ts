import { useCallback } from 'react';

export const useTTS = () => {
  const speak = useCallback((text: string, lang: string = 'en-US') => {
    // 停止之前的播放
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1.0;
    
    // 尋找對應語言的語音 (可選優化)
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find(v => v.lang === lang) || voices[0];
    if (voice) {
      utterance.voice = voice;
    }

    window.speechSynthesis.speak(utterance);
  }, []);

  return { speak };
};
