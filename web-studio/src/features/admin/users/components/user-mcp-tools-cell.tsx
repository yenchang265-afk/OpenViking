import type {
  AdminConnection,
  AdminUser,
  McpToolInfo,
  UserMcpTools,
} from '#/shared/api/admin'
import { fetchUserMcpTools, updateUserMcpTools } from '#/shared/api/admin'
import { getErrorMessage } from '#/shared/lib/error'
import { Badge } from '#/shared/ui/badge'
import { Button } from '#/shared/ui/button'
import { Checkbox } from '#/shared/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '#/shared/ui/dialog'
import { Switch } from '#/shared/ui/switch'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircleIcon, PencilIcon } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface UserMcpToolsCellProps {
  connection: AdminConnection
  user: AdminUser
}

export function UserMcpToolsCell({ connection, user }: UserMcpToolsCellProps) {
  const { t } = useTranslation('settings')
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const queryKey = [
    'user-mcp-tools',
    connection.baseUrl,
    connection.apiKey,
    user.accountId,
    user.userId,
  ]
  const query = useQuery({
    queryKey,
    queryFn: () => fetchUserMcpTools(connection, user.accountId, user.userId),
    retry: false,
  })
  const update = useMutation({
    mutationFn: (allowed: string[] | null) =>
      updateUserMcpTools(connection, user.accountId, user.userId, allowed),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKey, result)
      setOpen(false)
      toast.success(t('mcpTools.saved'))
    },
    onError: (error) =>
      toast.error(t('mcpTools.saveFailed'), {
        description: getErrorMessage(error),
      }),
  })
  if (query.isPending)
    return (
      <LoaderCircleIcon
        aria-label={t('loading')}
        className="size-4 animate-spin"
      />
    )
  if (query.isError)
    return (
      <Button
        variant="ghost"
        size="sm"
        title={getErrorMessage(query.error)}
        onClick={() => void query.refetch()}
      >
        {t('mcpTools.retry')}
      </Button>
    )
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        disabled={query.isFetching}
        onClick={async () => {
          const result = await query.refetch()
          if (result.isSuccess) setOpen(true)
        }}
        aria-label={t('mcpTools.editUser', { user: user.userId })}
      >
        <span className="decoration-dotted underline-offset-4 underline">
          {summarizeMcpTools(query.data, t)}
        </span>
        <PencilIcon className="size-3.5 text-primary" />
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!update.isPending) setOpen(next)
        }}
      >
        <DialogContent
          className="sm:max-w-2xl"
          showCloseButton={!update.isPending}
        >
          <DialogHeader>
            <DialogTitle>{t('mcpTools.edit')}</DialogTitle>
            <DialogDescription>
              {user.userId} · {t('mcpTools.description')}
            </DialogDescription>
          </DialogHeader>
          {open && (
            <McpToolsEditor
              value={query.data}
              disabled={update.isPending}
              onCancel={() => setOpen(false)}
              onSave={(allowed) => update.mutate(allowed)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

type Translate = ReturnType<typeof useTranslation>['t']

export function summarizeMcpTools(value: UserMcpTools, t: Translate): string {
  const allowed = value.allowed_tools
  if (allowed === null) return t('mcpTools.all')
  if (allowed.length === 0) return t('mcpTools.none')
  return t('mcpTools.some', {
    count: allowed.length,
    total: value.available_tools.length,
  })
}

interface McpToolsEditorProps {
  value: UserMcpTools
  disabled: boolean
  onCancel: () => void
  onSave: (allowed: string[] | null) => void
}

function McpToolsEditor({
  value,
  disabled,
  onCancel,
  onSave,
}: McpToolsEditorProps) {
  const { t } = useTranslation('settings')
  const tools = value.available_tools
  const [allowAll, setAllowAll] = useState(value.allowed_tools === null)
  const [selected, setSelected] = useState<ReadonlySet<string>>(
    () => new Set(value.allowed_tools ?? tools.map((tool) => tool.name)),
  )
  const toggle = (name: string, checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current)
      if (checked) next.add(name)
      else next.delete(name)
      return next
    })
  const choose = (pick: (tool: McpToolInfo) => boolean) =>
    setSelected(new Set(tools.filter(pick).map((tool) => tool.name)))
  return (
    <div className="flex flex-col gap-4">
      <label className="flex items-center gap-3 text-sm">
        <Switch
          checked={allowAll}
          disabled={disabled}
          onCheckedChange={setAllowAll}
        />
        {t('mcpTools.allowAll')}
      </label>
      {!allowAll && (
        <>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              onClick={() => choose(() => true)}
            >
              {t('mcpTools.selectAll')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              onClick={() => choose((tool) => tool.read_only)}
            >
              {t('mcpTools.selectReadOnly')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              onClick={() => choose(() => false)}
            >
              {t('mcpTools.clear')}
            </Button>
          </div>
          <ul className="max-h-[50vh] divide-y overflow-y-auto rounded-md border">
            {tools.map((tool) => (
              <li key={tool.name}>
                <label className="flex cursor-pointer items-start gap-3 px-3 py-2 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    checked={selected.has(tool.name)}
                    disabled={disabled}
                    onCheckedChange={(checked) => toggle(tool.name, checked)}
                    aria-label={tool.name}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 font-mono text-xs font-medium">
                      {tool.name}
                      {tool.read_only && (
                        <Badge variant="outline">
                          {t('mcpTools.readOnly')}
                        </Badge>
                      )}
                    </span>
                    <span className="line-clamp-2 text-xs text-muted-foreground">
                      {tool.description}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="outline" disabled={disabled} onClick={onCancel}>
          {t('mcpTools.cancel')}
        </Button>
        <Button
          disabled={disabled}
          onClick={() =>
            onSave(
              allowAll
                ? null
                : tools
                    .map((tool) => tool.name)
                    .filter((name) => selected.has(name)),
            )
          }
        >
          {disabled && <LoaderCircleIcon className="size-4 animate-spin" />}
          {t('mcpTools.save')}
        </Button>
      </div>
    </div>
  )
}
