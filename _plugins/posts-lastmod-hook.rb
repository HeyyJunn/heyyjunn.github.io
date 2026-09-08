#!/usr/bin/env ruby
#
# Check for changed posts

Jekyll::Hooks.register :posts, :pre_render do |post|

  # Velog-managed posts carry their authoritative source timestamp.
  next if post.data.key?('last_modified_at')

  commit_num = `git rev-list --count HEAD "#{ post.path }"`

  if commit_num.to_i > 1
    lastmod_date = `git log -1 --pretty="%ad" --date=iso "#{ post.path }"`
    post.data['last_modified_at'] = lastmod_date
  end

end
