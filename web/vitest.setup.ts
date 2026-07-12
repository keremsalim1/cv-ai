import '@testing-library/jest-dom/vitest'
import * as matchers from '@testing-library/jest-dom/matchers'
import { expect } from 'vitest'

// jest-dom's /vitest entry doesn't auto-extend under Vitest 4; extend explicitly.
expect.extend(matchers)

process.env.NEXT_PUBLIC_SUPABASE_URL ||= 'http://localhost:54321'
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||= 'test-anon-key'
process.env.NEXT_PUBLIC_API_URL ||= 'http://localhost:8000'
