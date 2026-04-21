interface Props { content: string; }
export function UserBubble({ content }: Props) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-blue-600 p-4">
        <p className="text-sm text-white whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
