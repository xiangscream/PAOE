declare module 'child_process' {
  export function spawn(command: string, args?: string[], options?: any): any
}

declare module 'http' {
  const http: any
  export default http
}

declare module 'https' {
  const https: any
  export default https
}

declare module 'fs' {
  export function existsSync(path: string): boolean
  export function readFileSync(path: string, encoding: string): string
}

declare module 'os' {
  export function homedir(): string
}

declare module 'path' {
  const path: {
    resolve(...parts: string[]): string
    join(...parts: string[]): string
    isAbsolute(value: string): boolean
  }
  export default path
}

declare const process: { env: Record<string, string | undefined> }

declare module '@codemirror/state' {
  export type Extension = any
  export type StateField<T = any> = any
}

declare module '@codemirror/view' {
  export type EditorView = any
  export type ViewPlugin<T = any> = any
}

declare module 'moment' {
  const moment: any
  export = moment
}
