declare module 'child_process' {
  export function spawn(command: string, args?: string[], options?: any): any
}

declare module 'fs' {
  export function mkdtempSync(prefix: string): string
  export function rmSync(path: string, options?: any): void
  export function writeFileSync(path: string, data: string, encoding?: string): void
}

declare module 'os' {
  export function tmpdir(): string
}

declare module 'path' {
  const path: {
    join(...parts: string[]): string
  }
  export default path
}

declare module 'http' {
  const http: any
  export default http
}

declare module 'https' {
  const https: any
  export default https
}
