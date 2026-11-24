import { ImageOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Renders a stored document. Documents are customer content, so:
 * - raw HTML is never rendered (no `rehype-raw`; react-markdown leaves it out);
 * - unsafe link schemes (`javascript:`) are dropped by react-markdown's default URL check;
 * - links open in a new tab without access to this page;
 * - images are not loaded: a remote one would tell its host who reads the document, and a
 *   relative one has nothing to point at here. Their alt text shows instead.
 */
/** An image's place: never loaded, its alt text shown (document content, as is). */
function ImageNotShown({ alt }: { alt: string | undefined }) {
  const { t } = useTranslation('document')
  return (
    <span className="bg-secondary text-muted-foreground not-prose inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-[13px]">
      <ImageOff aria-hidden="true" className="size-3.5" />
      {alt ? t('imageNotShownAlt', { alt }) : t('imageNotShown')}
    </span>
  )
}

const components: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  img: ({ alt }) => <ImageNotShown alt={alt} />,
}

export function Markdown({ source }: { source: string }) {
  return (
    <div className="markdown prose prose-sm max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  )
}
