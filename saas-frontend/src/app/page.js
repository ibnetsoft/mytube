export default function Home() {
  return (
    <main className="container" style={{ paddingTop: '80px', paddingBottom: '80px' }}>
      
      {/* Navigation */}
      <nav className="glass-panel flex-between" style={{ padding: '16px 32px', marginBottom: '60px', borderRadius: '100px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--gradient-brand)' }}></div>
          <span style={{ fontWeight: '800', fontSize: '1.2rem', letterSpacing: '1px' }}>PICADILLY<span className="text-muted" style={{ fontWeight: '400' }}>.AI</span></span>
        </div>
        <div style={{ display: 'flex', gap: '16px' }}>
          <button className="btn btn-secondary" style={{ padding: '8px 20px', fontSize: '0.9rem' }}>Dashboard</button>
          <button className="btn btn-primary" style={{ padding: '8px 20px', fontSize: '0.9rem' }}>Generate</button>
        </div>
      </nav>

      {/* Hero Section */}
      <section style={{ textAlign: 'center', marginBottom: '80px' }}>
        <div className="animate-fade-in-up" style={{ display: 'inline-block', padding: '6px 16px', background: 'rgba(0, 173, 181, 0.1)', color: 'var(--accent-primary)', borderRadius: '100px', fontSize: '0.85rem', fontWeight: '600', marginBottom: '24px', border: '1px solid rgba(0, 173, 181, 0.2)' }}>
          🚀 PICADILLY STUDIO SaaS VERSION 3.0
        </div>
        <h1 className="heading-lg animate-fade-in-up delay-100" style={{ marginBottom: '24px' }}>
          Create Cinematic Content<br />
          <span className="text-gradient">At the Speed of Thought.</span>
        </h1>
        <p className="text-muted animate-fade-in-up delay-200" style={{ fontSize: '1.2rem', maxWidth: '600px', margin: '0 auto 40px auto' }}>
          The next-generation AI video production platform. Automate scripts, storyboards, voiceovers, and rendering entirely in the cloud.
        </p>
        <div className="flex-center animate-fade-in-up delay-300" style={{ gap: '16px' }}>
          <button className="btn btn-primary" style={{ padding: '16px 32px', fontSize: '1.1rem' }}>Start Creating Free</button>
          <button className="btn btn-secondary" style={{ padding: '16px 32px', fontSize: '1.1rem' }}>View Demos</button>
        </div>
      </section>

      {/* Feature Grid */}
      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', opacity: 0 }} className="animate-fade-in-up delay-300">
        
        <div className="glass-card" style={{ padding: '32px' }}>
          <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(0, 173, 181, 0.1)', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px', marginBottom: '20px' }}>
            📝
          </div>
          <h3 style={{ fontSize: '1.25rem', marginBottom: '12px', fontWeight: '700' }}>AI Script Generation</h3>
          <p className="text-muted" style={{ fontSize: '0.95rem' }}>
            Powered by Gemini Pro 3.1. Automatically craft engaging long-form scripts tailored for YouTube SEO and high retention.
          </p>
        </div>

        <div className="glass-card" style={{ padding: '32px' }}>
          <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(0, 173, 181, 0.1)', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px', marginBottom: '20px' }}>
            🎙️
          </div>
          <h3 style={{ fontSize: '1.25rem', marginBottom: '12px', fontWeight: '700' }}>Expressive TTS</h3>
          <p className="text-muted" style={{ fontSize: '0.95rem' }}>
            Multi-character emotional voice synthesis using ElevenLabs Turbo v2.5. Brings your scripts to life instantly.
          </p>
        </div>

        <div className="glass-card" style={{ padding: '32px' }}>
          <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(0, 173, 181, 0.1)', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px', marginBottom: '20px' }}>
            🎬
          </div>
          <h3 style={{ fontSize: '1.25rem', marginBottom: '12px', fontWeight: '700' }}>Cinematic Engine</h3>
          <p className="text-muted" style={{ fontSize: '0.95rem' }}>
            Dual-keyframe prompt generation with Imagen 3 and Veo. Assemble breathtaking visuals in 16:9 format with dynamic pans and zooms.
          </p>
        </div>

      </section>

    </main>
  );
}
