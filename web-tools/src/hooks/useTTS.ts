import { useCallback } from 'react';

export const useTTS = () => {
  const speak = useCallback((text: string, lang: string = 'en-US') => {
    // 停止之前的播放
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1.0;
    
    // 獲取當前支援的所有語音清單
    const voices = window.speechSynthesis.getVoices();
    
    // 過濾出符合語言的語音清單
    const langVoices = voices.filter(v => v.lang.startsWith(lang.split('-')[0]));
    
    // 優先權選取邏輯
    const voice = 
      langVoices.find(v => v.name.includes('Google') && v.lang === lang) || // 優先用 Google
      langVoices.find(v => v.name.includes('Enhanced') || v.name.includes('Premium')) || // 次優先高品質
      langVoices.find(v => v.lang === lang) || // 符合語言的
      langVoices[0] || // 該語言群組第一個
      voices[0]; // 最終後備
    if (voice) {
      utterance.voice = voice;
    }

    window.speechSynthesis.speak(utterance);
  }, []);

  return { speak };
};
