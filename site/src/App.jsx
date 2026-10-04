import React, { useState } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import BehavioralComparisonDemo from './components/BehavioralComparisonDemo';
import ContractVisualizer from './components/ContractVisualizer';
import DocumentationHub from './components/DocumentationHub';
import DocSearchModal from './components/DocSearchModal';
import Footer from './components/Footer';

export default function App() {
  const [activeTab, setActiveTab] = useState('home'); // 'home' | 'playground' | 'docs'
  const [activeDocSection, setActiveDocSection] = useState('quickstart');
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const handleNavigateDoc = (tab, docSection = 'quickstart') => {
    setActiveTab(tab);
    if (docSection) {
      setActiveDocSection(docSection);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Sticky Navigation */}
      <Navbar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        onOpenSearch={() => setIsSearchOpen(true)}
      />

      {/* Main Body View */}
      <div style={{ flex: 1 }}>
        {activeTab === 'home' && (
          <main className="animate-fade-in">
            <Hero 
              onGetStarted={() => handleNavigateDoc('docs', 'quickstart')}
              onExploreSimulator={() => handleNavigateDoc('playground')}
            />
            <BehavioralComparisonDemo />
            <ContractVisualizer />
          </main>
        )}

        {activeTab === 'playground' && (
          <main className="animate-fade-in" style={{ paddingTop: '2rem' }}>
            <BehavioralComparisonDemo />
            <ContractVisualizer />
          </main>
        )}

        {activeTab === 'docs' && (
          <main className="animate-fade-in">
            <DocumentationHub initialDoc={activeDocSection} />
          </main>
        )}
      </div>

      {/* Footer */}
      <Footer onNavigate={handleNavigateDoc} />

      {/* Doc Search Modal */}
      <DocSearchModal 
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectDoc={(docId) => handleNavigateDoc('docs', docId)}
      />
    </div>
  );
}
