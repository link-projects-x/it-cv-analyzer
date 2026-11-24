import { useState } from 'react'
import type { MatchResponse } from './types'
import { ResultsScreen } from './components/ResultsScreen'

export function App({ response, onNewCv }: { response: MatchResponse; onNewCv?: () => void }) {
  const [shown, setShown] = useState(response)
  const rematch = shown.rematch
  // key: another category is a new set of vacancies and sliders, so the results screen starts over.
  return (
    <ResultsScreen
      key={shown.category ?? 'all'}
      response={shown}
      onNewCv={onNewCv}
      onCategoryChange={rematch ? (category) => setShown(rematch(category)) : undefined}
    />
  )
}
