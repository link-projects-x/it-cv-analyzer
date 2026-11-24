// There is no API yet: the page reads the example response from contracts/.
import example from '@contracts/examples/match-response.example.json'
import type { MatchResponse } from './types'

export const exampleResponse = example as MatchResponse
