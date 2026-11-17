declare module 'child_process' {
  export function spawn(command: string, args?: string[], options?: any): any
}
