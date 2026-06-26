import { useTranslation } from 'react-i18next'
import { Button } from '@/components/form/Button'
import type { SaveStatus } from '@/hooks/useEditableConfig'

interface SaveButtonProps {
  status: SaveStatus
  onClick: () => void
}

export function SaveButton({ status, onClick }: SaveButtonProps) {
  const { t } = useTranslation()
  return (
    <Button onClick={onClick} disabled={status === 'saving'}>
      {t(status === 'saved' ? 'common.saved' : 'common.save')}
    </Button>
  )
}
