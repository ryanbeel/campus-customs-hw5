import { useId } from 'react'
import type { AgentName } from '../types'

// Fur and costume for each member of the court. Ryan Jr. is always black and white.
const LOOKS: Record<AgentName, {
  fur: string; light: string; eyes: string; stripes?: string; patches?: string[]; points?: string
}> = {
  boss: { fur: '#161616', light: '#fafafa', eyes: '#d7e34a' },
  facilities: { fur: '#8b9099', light: '#eceef1', eyes: '#f0a830', stripes: '#5d626b' },
  inventory: { fur: '#e8913a', light: '#fbe6cb', eyes: '#62b84a', stripes: '#b5621c' },
  accounting: { fur: '#f6f1ea', light: '#fffdf8', eyes: '#3d9be0', patches: ['#e0883a', '#2b2b2b'] },
  customer_service: { fur: '#efe2cc', light: '#fbf5ea', eyes: '#3d8fe0', points: '#5a4032' },
}

type Props = { agent: AgentName; size?: number; title?: string }

export default function Cat({ agent, size = 120, title }: Props) {
  const look = LOOKS[agent]
  const uid = useId().replace(/:/g, '')
  const headClip = `head-${uid}`
  const bodyClip = `body-${uid}`
  const ink = '#1d1a24'

  return (
    <svg viewBox="0 0 140 156" width={size} height={size * 156 / 140} role="img" aria-label={title ?? agent}
         className={`cat cat-${agent}`}>
      <defs>
        <clipPath id={headClip}><circle cx="70" cy="74" r="30" /></clipPath>
        <clipPath id={bodyClip}><ellipse cx="70" cy="120" rx="34" ry="28" /></clipPath>
      </defs>

      {/* Royal cape sits behind the king */}
      {agent === 'boss' && (
        <g>
          <path d="M32 98 C16 124 14 146 20 154 L120 154 C126 146 124 124 108 98 Z" fill="#b3122e" stroke={ink} strokeWidth="2" />
          <path d="M40 104 C30 126 30 144 34 154" stroke="#8c0d23" strokeWidth="3" fill="none" />
          <path d="M100 104 C110 126 110 144 106 154" stroke="#8c0d23" strokeWidth="3" fill="none" />
        </g>
      )}

      {/* Tail */}
      <path d="M100 136 C130 134 134 104 118 90" fill="none" stroke={look.points ?? look.fur} strokeWidth="10"
            strokeLinecap="round" className="cat-tail" />
      {agent === 'boss' && <circle cx="118" cy="90" r="5.5" fill={look.light} stroke={ink} strokeWidth="1.5" />}

      {/* Body */}
      <ellipse cx="70" cy="120" rx="34" ry="28" fill={look.fur} stroke={ink} strokeWidth="2" />
      <g clipPath={`url(#${bodyClip})`}>
        {look.stripes && [104, 114, 124].map(y => (
          <path key={y} d={`M38 ${y} q8 -4 14 0 M88 ${y} q8 -4 14 0`} stroke={look.stripes} strokeWidth="3.5" fill="none" strokeLinecap="round" />
        ))}
        {look.patches && <>
          <ellipse cx="44" cy="112" rx="14" ry="12" fill={look.patches[0]} />
          <ellipse cx="98" cy="128" rx="12" ry="10" fill={look.patches[1]} />
        </>}
      </g>
      {/* Chest */}
      <path d="M56 98 C60 118 80 118 84 98 C88 124 82 142 70 146 C58 142 52 124 56 98 Z" fill={look.light} />

      {/* Ears */}
      <path d="M43 62 L45 28 L65 48 Z" fill={look.points ?? look.fur} stroke={ink} strokeWidth="2" strokeLinejoin="round" />
      <path d="M97 62 L95 28 L75 48 Z" fill={look.points ?? look.fur} stroke={ink} strokeWidth="2" strokeLinejoin="round" />
      <path d="M48 56 L49 36 L61 48 Z" fill="#f4a6b7" />
      <path d="M92 56 L91 36 L79 48 Z" fill="#f4a6b7" />

      {/* Head */}
      <circle cx="70" cy="74" r="30" fill={look.fur} stroke={ink} strokeWidth="2" />
      <g clipPath={`url(#${headClip})`}>
        {agent === 'boss' && <path d="M70 44 C66 58 62 68 58 82 L82 82 C78 68 74 58 70 44 Z" fill={look.light} />}
        {look.stripes && <>
          <path d="M62 48 L64 58 M70 46 L70 58 M78 48 L76 58" stroke={look.stripes} strokeWidth="3" strokeLinecap="round" />
          <path d="M40 72 L50 74 M40 80 L50 80 M100 72 L90 74 M100 80 L90 80" stroke={look.stripes} strokeWidth="3" strokeLinecap="round" />
        </>}
        {look.patches && <>
          <ellipse cx="50" cy="56" rx="18" ry="14" fill={look.patches[0]} />
          <ellipse cx="94" cy="60" rx="12" ry="11" fill={look.patches[1]} />
        </>}
        {look.points && <ellipse cx="70" cy="86" rx="22" ry="20" fill={look.points} opacity=".85" />}
      </g>
      {/* Muzzle */}
      <ellipse cx="70" cy="86" rx="15" ry="11" fill={look.points ? '#d9c6aa' : look.light} />

      {/* Eyes (blink together) */}
      <g className="cat-eyes">
        <ellipse cx="58" cy="72" rx="6.5" ry="7.5" fill={look.eyes} stroke={ink} strokeWidth="1.2" />
        <ellipse cx="82" cy="72" rx="6.5" ry="7.5" fill={look.eyes} stroke={ink} strokeWidth="1.2" />
        <ellipse cx="58" cy="73" rx="2.3" ry="5.6" fill={ink} />
        <ellipse cx="82" cy="73" rx="2.3" ry="5.6" fill={ink} />
        <circle cx="60" cy="69.5" r="1.6" fill="#fff" />
        <circle cx="84" cy="69.5" r="1.6" fill="#fff" />
      </g>
      {/* Nose, mouth, whiskers */}
      <path d="M66 82 L74 82 L70 87 Z" fill="#ef8aa1" />
      <path d="M70 87 q-4 5 -8 2 M70 87 q4 5 8 2" stroke={ink} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <g stroke="#9b9b9b" strokeWidth="1.2" strokeLinecap="round">
        <path d="M56 86 L34 82 M56 90 L34 92 M84 86 L106 82 M84 90 L106 92" />
      </g>

      {/* Paws */}
      <ellipse cx="56" cy="146" rx="10" ry="6.5" fill={look.points ?? look.light} stroke={ink} strokeWidth="1.6" />
      <ellipse cx="84" cy="146" rx="10" ry="6.5" fill={look.points ?? look.light} stroke={ink} strokeWidth="1.6" />

      <Costume agent={agent} ink={ink} />
    </svg>
  )
}

function Costume({ agent, ink }: { agent: AgentName; ink: string }) {
  switch (agent) {
    case 'boss':
      return (
        <g>
          {/* Ermine collar */}
          <ellipse cx="70" cy="101" rx="30" ry="7" fill="#fbfbfb" stroke={ink} strokeWidth="1.5" />
          {[50, 62, 76, 88].map(x => <path key={x} d={`M${x} 99 l1.5 4 l-3 0 z`} fill={ink} />)}
          {/* Crown */}
          <path d="M46 50 L43 22 L57 36 L70 14 L83 36 L97 22 L94 50 Z" fill="#f5b700" stroke="#7a4b00" strokeWidth="2.2" strokeLinejoin="round" />
          <rect x="45" y="44" width="50" height="9" rx="2" fill="#e09b00" stroke="#7a4b00" strokeWidth="2" />
          <circle cx="70" cy="48.5" r="3.4" fill="#d7263d" />
          <circle cx="56" cy="48.5" r="2.4" fill="#2a7de1" />
          <circle cx="84" cy="48.5" r="2.4" fill="#2aa84a" />
          <circle cx="43" cy="22" r="2.4" fill="#fff4c2" stroke="#7a4b00" strokeWidth="1" />
          <circle cx="70" cy="14" r="2.6" fill="#fff4c2" stroke="#7a4b00" strokeWidth="1" />
          <circle cx="97" cy="22" r="2.4" fill="#fff4c2" stroke="#7a4b00" strokeWidth="1" />
          {/* Scepter */}
          <rect x="111" y="86" width="5" height="60" rx="2" fill="#f5b700" stroke="#7a4b00" strokeWidth="1.5" transform="rotate(10 113 116)" />
          <circle cx="108" cy="84" r="7" fill="#d7263d" stroke="#7a4b00" strokeWidth="2" />
          <path d="M108 72 V78 M105 75 H111" stroke="#f5b700" strokeWidth="2.4" strokeLinecap="round" />
        </g>
      )
    case 'facilities':
      return (
        <g>
          {/* Plume */}
          <path d="M70 40 C66 22 80 10 92 14 C82 18 80 26 82 36" fill="#d7263d" stroke={ink} strokeWidth="1.5" />
          {/* Helmet with raised visor */}
          <path d="M40 70 C38 36 102 36 100 70 L100 64 C98 60 42 60 40 64 Z" fill="#c9ced6" stroke="#5b6270" strokeWidth="2" />
          <path d="M40 70 C40 40 100 40 100 70" fill="#c9ced6" stroke="#5b6270" strokeWidth="2" />
          <rect x="38" y="58" width="64" height="8" rx="3" fill="#aab1bc" stroke="#5b6270" strokeWidth="1.8" />
          <rect x="67" y="58" width="6" height="22" rx="2" fill="#c9ced6" stroke="#5b6270" strokeWidth="1.5" />
          <circle cx="44" cy="62" r="1.6" fill="#5b6270" /><circle cx="96" cy="62" r="1.6" fill="#5b6270" />
          {/* Shield */}
          <path d="M22 104 L50 104 L50 124 C50 138 36 146 36 146 C36 146 22 138 22 124 Z" fill="#1f4fbf" stroke="#d4a017" strokeWidth="2.5" />
          <g fill="#fff">
            <ellipse cx="36" cy="128" rx="6" ry="5" />
            <circle cx="29.5" cy="119" r="2.4" /><circle cx="34" cy="116" r="2.4" />
            <circle cx="38.5" cy="116" r="2.4" /><circle cx="43" cy="119" r="2.4" />
          </g>
        </g>
      )
    case 'inventory':
      return (
        <g>
          {/* Squire's cap with a feather */}
          <path d="M42 58 C42 34 98 34 98 58 Z" fill="#3f8f4e" stroke={ink} strokeWidth="2" />
          <rect x="40" y="54" width="60" height="7" rx="3" fill="#2f6e3b" stroke={ink} strokeWidth="1.6" />
          <path d="M90 50 C102 34 114 30 118 24 C112 38 104 46 92 54 Z" fill="#f2c94c" stroke={ink} strokeWidth="1.4" />
          {/* Supply crate */}
          <rect x="88" y="114" width="36" height="28" rx="2" fill="#b47a3c" stroke={ink} strokeWidth="2" />
          <path d="M88 123 H124 M88 132 H124" stroke="#8a5a28" strokeWidth="2" />
          <text x="106" y="131" textAnchor="middle" fontSize="8" fontWeight="800" fill="#fff4d6" fontFamily="Nunito, sans-serif">SKU</text>
        </g>
      )
    case 'accounting':
      return (
        <g>
          {/* Scholar's beret with a tassel */}
          <ellipse cx="70" cy="47" rx="32" ry="11" fill="#6d28d9" stroke={ink} strokeWidth="2" />
          <circle cx="70" cy="37" r="4" fill="#6d28d9" stroke={ink} strokeWidth="1.5" />
          <path d="M98 46 C104 52 104 60 102 66" stroke="#f5b700" strokeWidth="2.4" fill="none" />
          <circle cx="102" cy="67" r="3" fill="#f5b700" />
          {/* Spectacles */}
          <g fill="none" stroke="#7a4b00" strokeWidth="2">
            <circle cx="58" cy="72" r="9" /><circle cx="82" cy="72" r="9" /><path d="M67 71 Q70 68 73 71" />
          </g>
          {/* Coin purse */}
          <path d="M20 120 C14 140 26 148 38 148 C50 148 58 140 50 120 C46 114 24 114 20 120 Z" fill="#9a6b3a" stroke={ink} strokeWidth="2" />
          <path d="M26 118 Q35 112 44 118" stroke="#f5b700" strokeWidth="3" fill="none" />
          <text x="36" y="139" textAnchor="middle" fontSize="15" fontWeight="800" fill="#f5d36b" fontFamily="Nunito, sans-serif">$</text>
          {/* Quill */}
          <path d="M104 146 L120 104 C126 112 124 124 112 134 Z" fill="#fff" stroke={ink} strokeWidth="1.4" />
        </g>
      )
    case 'customer_service':
      return (
        <g>
          {/* Ruff collar */}
          <path d="M40 100 l6 -6 l6 6 l6 -6 l6 6 l6 -6 l6 6 l6 -6 l6 6 l6 -6 l6 6 l-6 6 h-48 z" fill="#f5b700" stroke={ink} strokeWidth="1.5" />
          {/* Jester hat with bells */}
          <path d="M42 56 C34 40 22 34 12 32 C26 26 46 30 58 44 Z" fill="#d7263d" stroke={ink} strokeWidth="2" strokeLinejoin="round" />
          <path d="M98 56 C106 40 118 34 128 32 C114 26 94 30 82 44 Z" fill="#f5b700" stroke={ink} strokeWidth="2" strokeLinejoin="round" />
          <path d="M44 58 C46 36 94 36 96 58 Z" fill="#2e8b57" stroke={ink} strokeWidth="2" />
          <path d="M42 56 l7 -5 l7 5 l7 -5 l7 5 l7 -5 l7 5 l7 -5 l7 5" fill="none" stroke={ink} strokeWidth="1.5" />
          <circle cx="12" cy="32" r="4.5" fill="#f5d36b" stroke={ink} strokeWidth="1.5" className="bell" />
          <circle cx="128" cy="32" r="4.5" fill="#f5d36b" stroke={ink} strokeWidth="1.5" className="bell" />
          <circle cx="70" cy="34" r="4" fill="#f5d36b" stroke={ink} strokeWidth="1.5" className="bell" />
        </g>
      )
  }
}
